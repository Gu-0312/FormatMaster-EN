# -*- coding: utf-8 -*-
"""_fmt_n format specifier 回归测试。

历史上 _fmt_n 曾因正则捕获组包含前导冒号导致 format() ValueError
（记忆教训：":04d" 传给 format() 报错，已用 [1:]/lstrip(":") 修复）。
此测试通过 core.tools.batch_rename 公共 API 间接覆盖 _fmt_n 全部分支，
确保 {n}、{n:04d}、{n:x}、{n:b} 等模板不再出错。

注：main.py:_rn_calc_name 内的 _fmt_n 逻辑与 batch_rename 内的一致
（[1:] 与 lstrip(":") 等价），测 batch_rename 即覆盖核心回归点。
"""
import os
import pytest
from core.tools import batch_rename


def _make_file(tmp_path, name):
    """在 tmp_path 下创建空文件，返回完整路径。"""
    p = os.path.join(str(tmp_path), name)
    with open(p, "w", encoding="utf-8") as f:
        f.write("x")
    return p


def _renamed_names(renamed):
    """从 batch_rename 返回值提取新文件名列表。"""
    return [os.path.basename(new) for _, new in renamed]


class TestFmtNSpecifier:
    """{n:spec} format specifier 回归——曾出 bug 的核心。"""

    def test_plain_n(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "file_{n}", start_num=1)
        assert _renamed_names(result) == ["file_1.jpg"]

    def test_n_zero_padded_4(self, tmp_path):
        # 曾 bug：{n:04d} 触发 ValueError
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "file_{n:04d}", start_num=1)
        assert _renamed_names(result) == ["file_0001.jpg"]

    def test_n_zero_padded_3(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "img_{n:03d}", start_num=5)
        assert _renamed_names(result) == ["img_005.jpg"]

    def test_n_hex(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "h_{n:x}", start_num=16)
        assert _renamed_names(result) == ["h_10.jpg"]

    def test_n_binary(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "b_{n:b}", start_num=5)
        assert _renamed_names(result) == ["b_101.jpg"]

    def test_n_large_start(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "{n:06d}", start_num=999999)
        assert _renamed_names(result) == ["999999.jpg"]


class TestBatchRenamePlaceholders:
    """其他占位符与组合。"""

    def test_name_placeholder(self, tmp_path):
        files = [_make_file(tmp_path, "photo.jpg")]
        result = batch_rename(files, "new_{name}", start_num=1)
        assert _renamed_names(result) == ["new_photo.jpg"]

    def test_ext_placeholder(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "file{ext}", start_num=1)
        assert _renamed_names(result) == ["file.jpg"]

    def test_combined_name_and_n(self, tmp_path):
        files = [_make_file(tmp_path, "vacation.png")]
        result = batch_rename(files, "{name}_{n:03d}", start_num=1)
        assert _renamed_names(result) == ["vacation_001.png"]

    def test_sequence_increments(self, tmp_path):
        files = [_make_file(tmp_path, f"f{i}.jpg") for i in range(3)]
        result = batch_rename(files, "item_{n:03d}", start_num=1)
        assert _renamed_names(result) == ["item_001.jpg", "item_002.jpg", "item_003.jpg"]

    def test_start_num_offset(self, tmp_path):
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "{n}", start_num=100)
        assert _renamed_names(result) == ["100.jpg"]


class TestBatchRenameTransforms:
    """查找替换 / 正则 / 大小写。"""

    def test_search_replace(self, tmp_path):
        files = [_make_file(tmp_path, "old_name.jpg")]
        result = batch_rename(files, "{name}", start_num=1,
                              search_text="old", replace_text="new")
        assert _renamed_names(result) == ["new_name.jpg"]

    def test_case_upper(self, tmp_path):
        # 用 output_dir 隔离：Windows 文件系统大小写不敏感，
        # 原地大小写转换会被 os.path.exists 判定为已存在而跳过。
        # 修复后大小写只作用于文件名主体，扩展名保留原样 → PHOTO.jpg
        out_dir = os.path.join(str(tmp_path), "out")
        os.makedirs(out_dir)
        files = [_make_file(tmp_path, "photo.jpg")]
        result = batch_rename(files, "{name}", start_num=1, case="upper", output_dir=out_dir)
        assert _renamed_names(result) == ["PHOTO.jpg"]

    def test_case_lower(self, tmp_path):
        out_dir = os.path.join(str(tmp_path), "out")
        os.makedirs(out_dir)
        files = [_make_file(tmp_path, "PHOTO.JPG")]
        result = batch_rename(files, "{name}", start_num=1, case="lower", output_dir=out_dir)
        # 扩展名保留原大写 → .JPG（修复后不再动扩展名）
        assert _renamed_names(result) == ["photo.JPG"]

    def test_case_title(self, tmp_path):
        out_dir = os.path.join(str(tmp_path), "out")
        os.makedirs(out_dir)
        files = [_make_file(tmp_path, "my photo.jpg")]
        result = batch_rename(files, "{name}", start_num=1, case="title", output_dir=out_dir)
        # 修复后扩展名保留原样 → .jpg（不再变成 .Jpg）
        assert _renamed_names(result) == ["My Photo.jpg"]

    def test_regex_replace(self, tmp_path):
        files = [_make_file(tmp_path, "img123.jpg")]
        result = batch_rename(files, "{name}", start_num=1,
                              regex_pattern=r"\d+", regex_replace="NUM")
        assert _renamed_names(result) == ["imgNUM.jpg"]

    def test_case_preserves_double_extension(self, tmp_path):
        # splitext 只切最后一段扩展名，.tar.gz 的 .tar 部分属文件名主体会被转换
        # 这是 os.path.splitext 的标准行为，测试如实记录
        out_dir = os.path.join(str(tmp_path), "out")
        os.makedirs(out_dir)
        files = [_make_file(tmp_path, "archive.tar.gz")]
        result = batch_rename(files, "{name}", start_num=1, case="upper", output_dir=out_dir)
        # body="archive.tar" 被 upper → ARCHIVE.TAR，ext=".gz" 保留
        assert _renamed_names(result) == ["ARCHIVE.TAR.gz"]

    def test_case_none_no_change(self, tmp_path):
        out_dir = os.path.join(str(tmp_path), "out")
        os.makedirs(out_dir)
        files = [_make_file(tmp_path, "Photo.jpg")]
        result = batch_rename(files, "{name}", start_num=1, case="none", output_dir=out_dir)
        assert _renamed_names(result) == ["Photo.jpg"]


class TestBatchRenameEdgeCases:
    """边界情况。"""

    def test_no_extension(self, tmp_path):
        files = [_make_file(tmp_path, "noext")]
        result = batch_rename(files, "file_{n}", start_num=1)
        assert _renamed_names(result) == ["file_1"]

    def test_skip_when_target_exists(self, tmp_path):
        # 目标已存在则跳过（不覆盖）
        _make_file(tmp_path, "target.jpg")
        files = [_make_file(tmp_path, "source.jpg")]
        result = batch_rename(files, "target", start_num=1)
        assert result == []  # 未重命名

    def test_empty_list(self, tmp_path):
        result = batch_rename([], "{n}", start_num=1)
        assert result == []

    def test_progress_callback_invoked(self, tmp_path):
        calls = []
        files = [_make_file(tmp_path, f"f{i}.jpg") for i in range(3)]
        batch_rename(files, "{n:03d}", start_num=1,
                     progress_cb=lambda pct, msg: calls.append((pct, msg)))
        assert len(calls) >= 2  # 至少有过程调用和完成调用

    def test_output_dir(self, tmp_path):
        out_dir = os.path.join(str(tmp_path), "out")
        os.makedirs(out_dir)
        files = [_make_file(tmp_path, "a.jpg")]
        result = batch_rename(files, "renamed_{n}", start_num=1, output_dir=out_dir)
        assert len(result) == 1
        assert os.path.dirname(result[0][1]) == out_dir
        assert os.path.basename(result[0][1]) == "renamed_1.jpg"
