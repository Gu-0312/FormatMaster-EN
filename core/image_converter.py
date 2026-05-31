"""图片格式转换"""
import os
from PIL import Image

class ImageConverter:
    def __init__(self):
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def convert(self, input_path, output_path, quality=95, resize=None,
                progress_callback=None):
        self._cancel = False
        try:
            img = Image.open(input_path)

            if self._cancel:
                if progress_callback:
                    progress_callback(-1, "已取消")
                return False

            if progress_callback:
                progress_callback(30, "处理中...")

            if img.mode == 'RGBA' and output_path.lower().endswith(('.jpg', '.jpeg', '.bmp')):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[3])
                img = bg
            elif img.mode not in ('RGB', 'RGBA', 'L', 'P'):
                img = img.convert('RGB')

            if resize:
                img = img.resize(resize, Image.LANCZOS)

            if self._cancel:
                if progress_callback:
                    progress_callback(-1, "已取消")
                return False

            if progress_callback:
                progress_callback(60, "保存中...")

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

        except Exception as e:
            if progress_callback:
                progress_callback(-1, f"错误: {e}")
            return False

    def batch_convert(self, files, output_dir, fmt_ext, quality=95,
                      resize=None, progress_callback=None):
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

            if self.convert(fp, out, quality, resize, file_progress):
                success += 1

        if progress_callback:
            progress_callback(100, f"完成 {success}/{total}")
        return success, total
