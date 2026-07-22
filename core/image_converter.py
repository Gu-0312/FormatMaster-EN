"""图片格式转换"""
import os
from PIL import Image, ImageDraw, ImageFont

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
            except:
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
                resize_factor=1.0,
                progress_callback=None):
        self._cancel = False
        try:
            img = Image.open(input_path)

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
                width, height = img.size
                new_width = int(width * resize_factor)
                new_height = int(height * resize_factor)
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
            elif ext == '.tiff':
                save_kwargs['compression'] = 'tiff_lzw'

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
