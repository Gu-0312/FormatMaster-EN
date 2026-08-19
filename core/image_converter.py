"""图片格式转换"""
import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageFilter

# HEIC/HEIF 支持（iPhone 照片格式；未安装 pillow-heif 时自动降级，不影响其他格式）
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

class ImageConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _add_watermark(self, img, text, position):
        if not text:
            return img
        
        try:
            draw = ImageDraw.Draw(img)
            img_width, img_height = img.size
            
            font_size = max(20, int(min(img_width, img_height) * 0.05))
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            
            text_bbox = draw.textbbox((0, 0), text, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            padding = 20
            pos_map = {
                "右下角": (img_width - text_width - padding, img_height - text_height - padding),
                "左下角": (padding, img_height - text_height - padding),
                "右上角": (img_width - text_width - padding, padding),
                "左上角": (padding, padding),
                "居中": ((img_width - text_width) // 2, (img_height - text_height) // 2)
            }
            
            x, y = pos_map.get(position, pos_map["右下角"])
            
            if img.mode == 'RGBA':
                draw.text((x, y), text, fill=(255, 255, 255, 180), font=font)
            else:
                draw.text((x, y), text, fill=(255, 255, 255), font=font)
                
        except Exception:
            pass
        
        return img

    def convert(self, input_path, output_path, quality=95, resize=None,
                watermark_text=None, watermark_position="右下角",
                rotate=0, crop_mode="原始比例", grayscale=False,
                resize_factor=1.0, strip_exif=False,
                progress_callback=None,
                contrast=1.0, saturation=1.0, sharpness=1.0, effect=""):
        """图片格式转换。

        contrast/saturation/sharpness: 增强系数（1.0=不变）。
        effect: 特效滤镜（"" 无 / hflip 水平翻转 / vflip 垂直翻转 /
                invert 反色 / emboss 浮雕 / edges 边缘检测 / sharpen 锐化）。
        """
        self._cancel = False
        try:
            # with + copy：完整解码后释放句柄，后续处理链与源文件解耦
            # （输出可能覆盖 input_path，Windows 下未关句柄会 PermissionError）
            with Image.open(input_path) as _f:
                img = _f.copy()

            if self._cancel:
                if progress_callback:
                    progress_callback(-1, "已取消")
                return False

            if progress_callback:
                progress_callback(20, "处理中...")

            if img.mode == 'RGBA' and output_path.lower().endswith(('.jpg', '.jpeg', '.bmp')):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode not in ('RGB', 'RGBA', 'L', 'P'):
                img = img.convert('RGB')

            if rotate != 0:
                img = img.rotate(rotate, expand=True)
                if progress_callback:
                    progress_callback(25, f"旋转{rotate}°...")

            if crop_mode == "裁剪为正方形":
                width, height = img.size
                size = min(width, height)
                left = (width - size) // 2
                top = (height - size) // 2
                right = left + size
                bottom = top + size
                img = img.crop((left, top, right, bottom))
                if progress_callback:
                    progress_callback(30, "裁剪为正方形...")

            if grayscale:
                img = img.convert('L')
                if progress_callback:
                    progress_callback(35, "转为灰度...")

            if resize_factor != 1.0:
                if resize_factor <= 0:
                    img.close()
                    raise ValueError("resize_factor 必须大于 0")
                width, height = img.size
                new_width = max(1, int(width * resize_factor))
                new_height = max(1, int(height * resize_factor))
                img = img.resize((new_width, new_height), Image.LANCZOS)
                if progress_callback:
                    progress_callback(40, f"缩放{int(resize_factor*100)}%...")
            elif resize:
                img = img.resize(resize, Image.LANCZOS)
                if progress_callback:
                    progress_callback(40, "调整大小...")

            if self._cancel:
                if progress_callback:
                    progress_callback(-1, "已取消")
                return False

            if watermark_text:
                img = self._add_watermark(img, watermark_text, watermark_position)
                if progress_callback:
                    progress_callback(50, "添加水印...")

            # 增强（对比度/饱和度/锐度）
            if abs(contrast - 1.0) > 0.01:
                img = ImageEnhance.Contrast(img).enhance(float(contrast))
            if abs(saturation - 1.0) > 0.01:
                img = ImageEnhance.Color(img).enhance(float(saturation))
            if abs(sharpness - 1.0) > 0.01:
                img = ImageEnhance.Sharpness(img).enhance(float(sharpness))

            # 特效滤镜
            if effect:
                img = self._apply_effect(img, effect)
                if progress_callback:
                    progress_callback(55, f"特效 {effect}...")

            if self._cancel:
                if progress_callback:
                    progress_callback(-1, "已取消")
                return False

            if progress_callback:
                progress_callback(70, "保存中...")

            save_kwargs = {}
            ext = os.path.splitext(output_path)[1].lower()
            if ext in ('.jpg', '.jpeg'):
                save_kwargs['quality'] = quality
                save_kwargs['optimize'] = True
            elif ext == '.png':
                save_kwargs['optimize'] = True
            elif ext == '.webp':
                save_kwargs['quality'] = quality
            elif ext == '.avif':
                # AVIF 编码依赖 pillow-avif-plugin（requirements 已加入）
                save_kwargs['quality'] = quality
            elif ext in ('.heic', '.heif'):
                # HEIC 编码依赖 pillow-heif
                save_kwargs['quality'] = quality
            elif ext == '.tiff':
                save_kwargs['compression'] = 'tiff_lzw'

            if strip_exif:
                # 清除拍摄设备/GPS 等隐私元数据（EXIF/ICC），仅保留像素
                img.info.pop('exif', None)
                img.info.pop('icc_profile', None)
                img.info.pop('photoshop', None)
                if ext in ('.jpg', '.jpeg', '.webp'):
                    save_kwargs['exif'] = b''

            img.save(output_path, **save_kwargs)
            img.close()

            if progress_callback:
                progress_callback(100, "转换完成")
            return True

        except FileNotFoundError:
            if progress_callback:
                progress_callback(-1, "错误：找不到输入图片文件")
            return False
        except (IOError, OSError) as e:
            if progress_callback:
                msg = "文件无法打开或保存，文件可能已损坏或被占用"
                progress_callback(-1, f"错误：{msg}（{e}）")
            return False
        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误：{e}")
            return False

    @staticmethod
    def _apply_effect(img, effect):
        """应用一键特效（翻转/反色/浮雕/边缘/锐化）。"""
        img = img.convert("RGB")
        try:
            if effect == "hflip":
                return ImageOps.mirror(img)
            if effect == "vflip":
                return ImageOps.flip(img)
            if effect == "invert":
                return ImageOps.invert(img)
            if effect == "emboss":
                return img.filter(ImageFilter.EMBOSS)
            if effect == "edges":
                return img.filter(ImageFilter.FIND_EDGES).point(lambda p: 255 - p)
            if effect == "sharpen":
                return img.filter(ImageFilter.UnsharpMask(radius=2, percent=150))
        except Exception:
            return img
        return img

    def batch_convert(self, files, output_dir, fmt_ext, quality=95,
                      resize=None, rotate=0, crop_mode="原始比例", grayscale=False,
                      progress_callback=None):
        self._cancel = False
        total = len(files)
        success = 0

        for i, fp in enumerate(files):
            if self._cancel:
                if progress_callback:
                    progress_callback(-1, f"已取消 ({success}/{total})")
                return success, total

            name = os.path.splitext(os.path.basename(fp))[0]
            out = os.path.join(output_dir, name + fmt_ext)

            def file_progress(pct, msg):
                overall = int((i * 100 + pct) / total)
                if progress_callback:
                    progress_callback(overall, f"[{i+1}/{total}] {msg}")

            if self.convert(fp, out, quality, resize, rotate=rotate, 
                           crop_mode=crop_mode, grayscale=grayscale, 
                           progress_callback=file_progress):
                success += 1

        if progress_callback:
            progress_callback(100, f"完成 {success}/{total}")
        return success, total
