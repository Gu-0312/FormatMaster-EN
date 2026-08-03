# -*- coding: utf-8 -*-
"""app/exceptions.py 异常映射测试。

覆盖 _hint_ex 映射命中与未命中、EX_HINT 字典完整性。
"""
import pytest
from app.exceptions import EX_HINT, _hint_ex


class TestHintEx:
    def test_file_not_found(self):
        assert _hint_ex(FileNotFoundError("x")) == "找不到输入文件，请检查路径"

    def test_permission_error(self):
        assert _hint_ex(PermissionError("x")) == "没有访问权限，请检查文件/目录权限"

    def test_value_error(self):
        assert _hint_ex(ValueError("x")) == "参数值不合法，请检查输入"

    def test_key_error(self):
        assert _hint_ex(KeyError("x")) == "缺少必要参数，请检查设置"

    def test_os_error(self):
        assert _hint_ex(OSError("x")) == "系统错误，文件可能被占用或路径无效"

    def test_type_error(self):
        assert _hint_ex(TypeError("x")) == "类型错误，数据格式不匹配"

    def test_runtime_error(self):
        assert _hint_ex(RuntimeError("x")) == "运行时错误，文件可能已损坏或不支持"

    def test_unmapped_returns_none(self):
        class CustomError(Exception):
            pass
        assert _hint_ex(CustomError("x")) is None

    def test_subclass_matches(self):
        # FileNotFoundError 是 OSError 子类，应优先匹配更具体的
        # _hint_ex 遍历 EX_HINT，k in en 检查子串
        result = _hint_ex(FileNotFoundError("x"))
        assert result is not None
        assert "找不到输入文件" in result


class TestExHintDict:
    def test_dict_not_empty(self):
        assert len(EX_HINT) > 0

    def test_all_values_are_str(self):
        for k, v in EX_HINT.items():
            assert isinstance(v, str), f"值非字符串: {k}"

    def test_all_keys_are_str(self):
        for k in EX_HINT.items():
            assert isinstance(k[0], str), f"键非字符串: {k}"

    def test_common_exceptions_covered(self):
        # 关键异常必须覆盖
        required = ["FileNotFoundError", "PermissionError", "ValueError",
                    "OSError", "RuntimeError", "TypeError"]
        for exc_name in required:
            assert any(exc_name in k for k in EX_HINT.keys()), \
                f"缺少关键异常映射: {exc_name}"
