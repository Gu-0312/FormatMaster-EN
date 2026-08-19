"""utils/format_helpers.py 纯逻辑测试：容量/文件大小格式化。"""

import datetime

from utils.format_helpers import (
    format_capacity_gb, format_datetime, format_physical_disk, format_size,
)


class TestFormatCapacityGb:
    def test_gb_small(self):
        assert format_capacity_gb(512) == "512 GB"
        assert format_capacity_gb(180.5) == "180 GB"  # 银行家舍入 180.5 → 180

    def test_gb_rounding(self):
        assert format_capacity_gb(128.5) == "128 GB"

    def test_tb_threshold(self):
        # >=1024 GB 转 TB
        assert format_capacity_gb(1024) == "1.0 TB"
        assert format_capacity_gb(2048) == "2.0 TB"
        assert format_capacity_gb(1536) == "1.5 TB"

    def test_string_input(self):
        assert format_capacity_gb("512") == "512 GB"
        assert format_capacity_gb("2048") == "2.0 TB"

    def test_invalid_input(self):
        assert format_capacity_gb(None) == "Unknown"
        assert format_capacity_gb("abc") == "Unknown"


class TestFormatSize:
    def test_bytes(self):
        assert format_size(500) == "500 B"

    def test_kb(self):
        assert format_size(2048) == "2.0 KB"

    def test_mb(self):
        assert format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gb(self):
        assert format_size(3 * 1024 ** 3) == "3.0 GB"


class TestFormatPhysicalDisk:
    def test_nvme(self):
        # 型号以右括号结尾（如 "HYV512X4 (GR)"）→ 容量括号前补空格
        assert format_physical_disk("", "NVMe HYV512X4 (GR)", 477) \
            == "NVMe HYV512X4 (GR) (477GB)"

    def test_nvme_with_model_prefix(self):
        # 型号以数字结尾 → 容量括号紧贴
        assert format_physical_disk(
            "", "NVMe WD PC SN740 SDDPNQD-512G-1002", 477) \
            == "NVMe WD PC SN740 SDDPNQD-512G-1002(477GB)"

    def test_interface_and_model(self):
        # 提供 interface 时拼接：SCSI 已被上层过滤，这里验证拼接逻辑
        assert format_physical_disk("NVMe", "Some Disk", 256) \
            == "NVMe Some Disk(256GB)"

    def test_empty_interface(self):
        # 无接口前缀（如 SATA 盘）：直接型号 + 容量
        assert format_physical_disk("", "Samsung SSD 870 EVO", 1000.0) \
            == "Samsung SSD 870 EVO(1000GB)"

    def test_invalid_size(self):
        # 容量非法时省略容量段
        assert format_physical_disk("NVMe", "Some Disk", None) \
            == "NVMe Some Disk"

    def test_empty_model(self):
        # 型号为空时省略型号（返回容量段）
        assert format_physical_disk("NVMe", "", 512) == "NVMe(512GB)"


class TestFormatDatetime:
    def test_today(self):
        s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        assert format_datetime(s).startswith("今天 ")

    def test_yesterday(self):
        s = (datetime.datetime.now() - datetime.timedelta(days=1)
             ).strftime("%Y-%m-%d %H:%M:%S")
        assert format_datetime(s).startswith("昨天 ")

    def test_older_full(self):
        assert format_datetime("2026-08-01 09:15:22") == "2026-08-01 09:15:22"

    def test_minute_only(self):
        # 无秒的格式：今天只显示到分钟
        s = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        assert format_datetime(s).startswith("今天 ")

    def test_invalid_passthrough(self):
        assert format_datetime("not-a-time") == "not-a-time"
        assert format_datetime("") == ""
        assert format_datetime(None) == ""


class TestRemoveHistory:
    def test_remove_history(self, tmp_path, monkeypatch):
        import utils.config as cfg
        monkeypatch.setattr(cfg, "get_user_data_dir", lambda: str(tmp_path))
        from core.m3u8_downloader import M3U8Store
        store = M3U8Store()
        store.add_history("https://a/x.m3u8", "A", "C:/out/a.mp4")
        store.add_history("https://b/y.m3u8", "B", "C:/out/b.mp4")
        assert len(store.get_history()) == 2
        store.remove_history("https://a/x.m3u8")
        hist = store.get_history()
        assert len(hist) == 1 and hist[0]["url"] == "https://b/y.m3u8"
        # 删除不存在的 URL 不报错
        store.remove_history("https://none/")
        assert len(store.get_history()) == 1

    def test_clear_history(self, tmp_path, monkeypatch):
        import utils.config as cfg
        monkeypatch.setattr(cfg, "get_user_data_dir", lambda: str(tmp_path))
        from core.m3u8_downloader import M3U8Store
        store = M3U8Store()
        store.add_history("https://a/x.m3u8", "A", "C:/out/a.mp4")
        store.clear_history()
        assert store.get_history() == []
