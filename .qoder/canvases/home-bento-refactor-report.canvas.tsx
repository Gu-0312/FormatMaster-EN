import { Callout, Divider, Grid, H1, H2, Stack, Stat, Table, Tag, Text } from 'qoder/canvas';

export default function HomeBentoRefactorReport() {
  return (
    <Stack gap={20}>
      <Stack gap={6}>
        <H1>首页 Bento Grid 重构 — 完成报告</H1>
        <Text tone="secondary">
          格式大师（FormatMaster）首页从线性堆叠卡片重构为 Bento Box Grid 非对称网格 + Soft UI
          柔和阴影组合风格，保留全部现有功能逻辑。
        </Text>
      </Stack>

      <Grid columns={4} gap={16}>
        <Stat value="128" label="pytest 通过" tone="success" />
        <Stat value="0" label="ruff 告警" tone="success" />
        <Stat value="20" label="功能入口（4 分组）" />
        <Stat value="~0.2s" label="主题切换耗时" />
      </Grid>

      <Divider />

      <H2>成果摘要</H2>
      <Stack gap={8}>
        <Text>
          1. 主题令牌扩展：app/theme.py 在 D / D_DARK 新增 Soft UI 令牌（card_hover、card_active、
          shadow_outer、shadow_inner、hero_gradient）与 4 组分组色（media / edit / tool / net），
          FONTS 新增 hero_title / stat_value / bento_label 字号；bento_gap 作为间距值放入 SPACING 字典。
        </Text>
        <Text>
          2. 新增 BentoCard 控件：gui/widgets.py 实现双层 Frame 模拟柔和阴影、hover 200ms
          颜色渐变插值（8 步 after 定时器）、主题重绘 redraw_theme、span_col / span_row 与
          grid_in 便捷布局方法。
        </Text>
        <Text>
          3. 重写 _p_home()：4 列 Bento 网格 — Row0 Hero 欢迎卡(2列)+今日转换+节省空间；Row1
          成功率+累计运行+快速拖放区(2列)；Row2-3 四组功能卡各占 2 列；Row4 最近任务全宽。
        </Text>
        <Text>
          4. 更新 _refresh_home()：统计刷新、分组子网格重建、最近任务列表刷新逻辑保留；
          色块颜色从 D 令牌读取，替代硬编码列表。
        </Text>
      </Stack>

      <Divider />

      <H2>变更文件</H2>
      <Table
        headers={['文件', '变更', '说明']}
        rows={[
          ['app/theme.py', '修改', '新增 15 个颜色令牌 + 3 个字号 + SPACING bento 间距'],
          ['gui/widgets.py', '修改', '新增颜色插值工具函数与 BentoCard 类'],
          ['main.py', '修改', '重写 _p_home() / _refresh_home()，更新 import'],
        ]}
      />

      <Divider />

      <H2>关键步骤与问题修复</H2>
      <Stack gap={8}>
        <Text>
          定位并修复运行时崩溃：D / D_DARK 中的 bento_gap 整数值违反「所有颜色令牌必须为十六进制
          字符串」约定，导致 _build_theme_color_map 的 classify_hex 调用 .upper() 报
          AttributeError；将其迁移至 SPACING 字典并更新 main.py 引用后解决。
        </Text>
        <Text>按计划补齐 BentoCard 的 span_col / span_row 参数与 grid_in() 便捷方法。</Text>
        <Text>
          最近任务卡片清空按钮布局修正：改为 body 内自建标题行（左标题 + 右清空按钮），
          避免按钮落在 header 与 body 之间。
        </Text>
      </Stack>

      <Divider />

      <H2>验证证据</H2>
      <Table
        headers={['验证项', '方式', '结果']}
        rows={[
          ['应用实例化', '运行时脚本实例化 FormatMaster 并 update_idletasks', '通过'],
          ['首页刷新', '调用 _refresh_home() 无异常', '通过'],
          ['主题切换', 'Light → Dark → Light 双向切换后重建首页', '通过（约 0.2s/次）'],
          ['功能卡点击跳转', 'event_generate 模拟 Button-1 触发 _switch', '通过'],
          ['拖放路由钩子', '_home_browse / _home_clear_recent 可调用', '通过'],
          ['静态检查', 'ruff check app gui main.py', 'All checks passed'],
          ['回归测试', 'pytest', '128 passed'],
        ]}
      />

      <Callout tone="success" title="最终结果">
        计划五大章节（主题令牌、BentoCard 控件、_p_home 重写、_refresh_home 更新、验证）全部实现
        并经运行时与静态验证确认；目标已标记完成。
      </Callout>

      <Stack gap={4}>
        <Text tone="secondary" size="small">计划文件：首页_Bento_Grid_重构_task-b83.md</Text>
        <Tag tone="success">Goal Complete</Tag>
      </Stack>
    </Stack>
  );
}
