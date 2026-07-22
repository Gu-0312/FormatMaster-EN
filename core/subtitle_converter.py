"""字幕转换 SRT ↔ ASS ↔ VTT"""
import os
import re

SRT_TIME = re.compile(r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})')
ASS_TIME = re.compile(r'(\d):(\d{2}):(\d{2})[.](\d{2})')

def _srt_time_to_ms(t):
    h, m, s, ms = int(t[0]), int(t[1]), int(t[2]), int(t[3])
    return h * 3600000 + m * 60000 + s * 1000 + ms

def _ms_to_srt_time(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _ms_to_ass_time(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    cs = (ms % 1000) // 10
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _ms_to_vtt_time(ms):
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def parse_srt(text):
    blocks = []
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        match = re.match(r'(\d+)', lines[0])
        if not match:
            continue
        idx = int(match.group(1))
        time_match = re.match(r'(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})', lines[1])
        if not time_match:
            continue
        start = _srt_time_to_ms(SRT_TIME.findall(time_match.group(1))[0])
        end = _srt_time_to_ms(SRT_TIME.findall(time_match.group(2))[0])
        text = '\n'.join(lines[2:])
        blocks.append({"start": start, "end": end, "text": text})
    return blocks


def to_srt(blocks):
    lines = []
    for i, b in enumerate(blocks, 1):
        lines.append(str(i))
        lines.append(f"{_ms_to_srt_time(b['start'])} --> {_ms_to_srt_time(b['end'])}")
        lines.append(b['text'])
        lines.append('')
    return '\n'.join(lines)


def to_ass(blocks):
    header = """[Script Info]
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Microsoft YaHei,24,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for b in blocks:
        start = _ms_to_ass_time(b['start'])
        end = _ms_to_ass_time(b['end'])
        text = b['text'].replace('\n', '\\N')
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return '\n'.join(lines)


def to_vtt(blocks):
    lines = ["WEBVTT", ""]
    for b in blocks:
        lines.append(f"{_ms_to_vtt_time(b['start'])} --> {_ms_to_vtt_time(b['end'])}")
        lines.append(b['text'])
        lines.append('')
    return '\n'.join(lines)


def convert_subtitle(input_path, output_path, progress_cb=None):
    try:
        ext = os.path.splitext(input_path)[1].lower()
        out_ext = os.path.splitext(output_path)[1].lower()
        with open(input_path, 'r', encoding='utf-8-sig') as f:
            content = f.read()

        if ext == '.srt':
            blocks = parse_srt(content)
        elif ext == '.ass':
            lines = content.split('\n')
            blocks = []
            in_events = False
            for line in lines:
                if line.strip().startswith('[Events]'):
                    in_events = True
                    continue
                if in_events and line.strip().startswith('['):
                    in_events = False
                if in_events and line.startswith('Dialogue:'):
                    parts = line.split(',', 9)
                    if len(parts) >= 10:
                        start_str = parts[1].strip()
                        end_str = parts[2].strip()
                        text = parts[9].strip().replace('\\N', '\n')
                        def _to_ms(t):
                            m = re.match(r'(\d+):(\d{2}):(\d{2})[.](\d{2})', t)
                            if m:
                                return int(m[1])*3600000+int(m[2])*60000+int(m[3])*1000+int(m[4])*10
                            return 0
                        blocks.append({"start": _to_ms(start_str), "end": _to_ms(end_str), "text": text})
        elif ext == '.vtt':
            text = re.sub(r'^WEBVTT.*\n?', '', content, flags=re.MULTILINE)
            blocks = parse_srt(text.replace('.', ','))
        else:
            if progress_cb:
                progress_cb(-1, f"不支持输入格式: {ext}")
            return False

        if out_ext == '.srt':
            result = to_srt(blocks)
        elif out_ext == '.ass':
            result = to_ass(blocks)
        elif out_ext == '.vtt':
            result = to_vtt(blocks)
        else:
            if progress_cb:
                progress_cb(-1, f"不支持输出格式: {out_ext}")
            return False

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(result)
        if progress_cb:
            progress_cb(100, "转换完成")
        return True
    except Exception as e:
        if progress_cb:
            progress_cb(-1, f"错误：{e}")
        return False