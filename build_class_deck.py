from pathlib import Path
import math
from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.oxml.ns import qn

ROOT = Path('/Users/qx/code/rec')
ASSETS = ROOT / 'deck-assets'
OUT = ROOT / '映刻-课堂分享.pptx'

# ---------- palette ----------
BG      = RGBColor(0x0E, 0x0D, 0x13)
PANEL   = RGBColor(0x17, 0x14, 0x1F)
PANEL2  = RGBColor(0x1E, 0x1A, 0x29)
TEXT    = RGBColor(0xF4, 0xF1, 0xFA)
MUTED   = RGBColor(0xA3, 0x9C, 0xB4)
DIM     = RGBColor(0x6C, 0x65, 0x7C)
ACCENT  = RGBColor(0xB7, 0xA4, 0xFF)
LIGHT   = RGBColor(0xE2, 0xD3, 0xFF)
LINE    = RGBColor(0x2D, 0x27, 0x3A)
CORAL   = RGBColor(0xFF, 0x9C, 0x9C)
GREEN   = RGBColor(0xB9, 0xF2, 0xC9)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)

FONT = 'PingFang SC'
MONO = 'Menlo'

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
prs.core_properties.title = '把每一次停留，变成下一次推荐'
prs.core_properties.author = '映刻 YINGKE'
prs.core_properties.subject = '映刻短视频推荐系统课程分享'

# ---------- helpers ----------
def slide_new():
    s = prs.slides.add_slide(prs.slide_layouts[6])
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    return s

def rect(s, x, y, w, h, fill=PANEL, line=None, radius=0.06, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    shp = s.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(0.8)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        try:
            shp.adjustments[0] = radius
        except Exception:
            pass
    return shp

def line(s, x1, y1, x2, y2, color=LINE, width=0.8):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    return c

def arrow(s, x, y, w=0.32, h=0.22, color=ACCENT):
    shp = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.shadow.inherit = False
    shp.fill.solid(); shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    return shp

def line_arrow(s, x1, y1, x2, y2, color=RGBColor(0x8A,0x75,0xC9), width=1.0):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    from pptx.oxml.xmlchemy import OxmlElement
    tail = OxmlElement('a:tailEnd')
    tail.set('type', 'triangle'); tail.set('w', 'sm'); tail.set('len', 'sm')
    ln.append(tail)
    return c

def style_run(run, size=14, color=TEXT, bold=False, font=FONT, italic=False, spacing=None):
    run.font.name = font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    ea = rPr.find(qn('a:ea'))
    if ea is None:
        from pptx.oxml.xmlchemy import OxmlElement
        ea = OxmlElement('a:ea')
        rPr.append(ea)
    ea.set('typeface', font)
    if spacing:
        rPr.set('spc', str(int(spacing * 100)))

def text(s, x, y, w, h, body, size=14, color=TEXT, bold=False, font=FONT,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, line_spacing=1.05,
         space_after=0, margins=(0, 0, 0, 0), italic=False, spacing=None):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left, tf.margin_right, tf.margin_top, tf.margin_bottom = [Inches(m) for m in margins]
    lines = body.split('\n')
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_before = Pt(0)
        p.space_after = Pt(space_after)
        r = p.add_run()
        r.text = ln
        style_run(r, size, color, bold, font, italic, spacing)
    return box

def rich(s, x, y, w, h, runs, size=14, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, line_spacing=1.05):
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear(); tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    p.alignment = align
    p.line_spacing = line_spacing
    p.space_before = Pt(0); p.space_after = Pt(0)
    for txt, color, bold, fsize, fnt in runs:
        r = p.add_run(); r.text = txt
        style_run(r, fsize if fsize else size, color, bold, fnt or FONT)
    return box

def pic_cover(s, path, x, y, w, h):
    iw, ih = Image.open(path).size
    target = w / h
    ratio = iw / ih
    p = s.shapes.add_picture(str(path), Inches(x), Inches(y), Inches(w), Inches(h))
    if ratio > target:
        excess = 1 - target / ratio
        p.crop_left = excess / 2; p.crop_right = excess / 2
    elif ratio < target:
        excess = 1 - ratio / target
        p.crop_top = excess / 2; p.crop_bottom = excess / 2
    return p

def label(s, x, y, w, body, color=ACCENT, size=9.5, spacing=2.2):
    text(s, x, y, w, 0.24, body, size=size, color=color, bold=True, spacing=spacing)

def footer(s, num, total=14):
    line(s, 0.72, 7.03, 12.6, 7.03, LINE, 0.6)
    text(s, 0.72, 7.12, 6.5, 0.22, '映刻 YINGKE  ·  课堂分享', 8.5, DIM)
    text(s, 11.72, 7.12, 0.9, 0.22, f'{num:02d} / {total:02d}', 8.5, DIM, align=PP_ALIGN.RIGHT)

def header(s, kicker, title, num, title_size=28):
    label(s, 0.72, 0.46, 8.0, kicker)
    text(s, 0.72, 0.76, 11.9, 0.62, title, title_size, TEXT, bold=True, line_spacing=0.98)
    rect(s, 0.72, 1.43, 0.34, 0.045, ACCENT, None, shape=MSO_SHAPE.RECTANGLE)
    footer(s, num)

def notes(s, body):
    s.notes_slide.notes_text_frame.text = body

def stat(s, x, y, w, value, unit, caption, color=ACCENT):
    text(s, x, y, w, 0.7, value, 38, color, bold=True, font=FONT, line_spacing=0.9)
    text(s, x + 0.02, y + 0.62, w, 0.26, unit, 10, MUTED)
    text(s, x, y + 0.95, w, 0.26, caption, 9.5, DIM)

def pill(s, x, y, w, body, size=9.5, color=ACCENT, fill=PANEL2):
    rect(s, x, y, w, 0.36, fill, LINE, 0.18)
    text(s, x + 0.16, y + 0.085, w - 0.3, 0.2, body, size, color, bold=True, spacing=1.2)

# ---------- 01 cover ----------
s = slide_new()
pic_cover(s, ASSETS / 'cover-frame.png', 0, 0, 13.333, 7.5)
s.shapes.add_picture(str(ASSETS / 'cover-overlay.png'), 0, 0, width=prs.slide_width, height=prs.slide_height)
s.shapes.add_picture(str(ASSETS / 'cover-veil.png'), 0, 0, width=prs.slide_width, height=prs.slide_height)
# brand mark + wordmark
rect(s, 0.78, 0.55, 0.12, 0.36, ACCENT, None, shape=MSO_SHAPE.RECTANGLE)
text(s, 0.98, 0.53, 2.2, 0.34, '映刻', 16, WHITE, bold=True)
text(s, 0.99, 0.82, 2.4, 0.22, 'Y I N G K E', 8.5, LIGHT, spacing=2.4)
text(s, 10.25, 0.57, 2.4, 0.24, 'COURSE DECK  /  2026', 8.5, LIGHT, align=PP_ALIGN.RIGHT, spacing=1.8)
# hero
label(s, 0.8, 1.62, 7.0, 'REAL-TIME RECOMMENDATION  /  课程分享')
text(s, 0.8, 1.92, 8.0, 0.92, '把每一次停留', 52, WHITE, bold=True, line_spacing=0.95)
text(s, 0.8, 2.83, 8.2, 0.95, '变成下一次推荐', 52, LIGHT, bold=True, line_spacing=0.95)
text(s, 0.82, 4.02, 7.1, 1.1,
     '映刻短视频推荐系统：从产品闭环，到 Flink SQL 实时链路。\n一次点赞，如何改变下一刷？',
     17, RGBColor(0xDD,0xD6,0xEA), line_spacing=1.55)
line(s, 0.82, 6.28, 6.55, 6.28, RGBColor(0x6E,0x61,0x82), 0.8)
text(s, 0.82, 6.46, 6.4, 0.26, 'FastAPI  ·  MySQL  ·  Kafka  ·  Flink SQL', 10.5, LIGHT)
text(s, 9.55, 6.46, 3.0, 0.26, '24 条短片  /  15 种算法  /  1 个实时作业', 9.5, RGBColor(0xC9,0xC0,0xD8), align=PP_ALIGN.RIGHT)
notes(s, '开场先不讲技术。先问：你刚点过一个赞，下一刷为什么不一样？让学生先猜，再告诉他们这节课会把这个问题拆成产品、数据和实时计算三层。')

# ---------- 02 product ----------
s = slide_new()
header(s, '01  /  PRODUCT SLICE', '先看产品：一个会记住你的信息流', 2)
pic_cover(s, ASSETS / 'dashboard-crop.png', 0.72, 1.62, 7.15, 4.86)
rect(s, 0.72, 1.62, 7.15, 4.86, None, RGBColor(0x3A,0x32,0x4C), 0.02)
text(s, 8.25, 1.66, 4.3, 0.24, 'PRODUCT LOOP', 9.5, ACCENT, bold=True, spacing=2.2)
items = [
    ('01', '身份', '登录后，才有属于你的推荐。'),
    ('02', '多路', '混合推荐，15 种算法做候选。'),
    ('03', '反馈', '点赞、收藏、完播，立刻进入特征。'),
    ('04', '解释', '推荐理由，让结果可以被追问。'),
]
for i, (n, h, b) in enumerate(items):
    yy = 2.03 + i * 1.03
    text(s, 8.25, yy, 0.45, 0.24, n, 10.5, ACCENT, bold=True, font=MONO)
    text(s, 8.75, yy - 0.04, 4.0, 0.3, h, 15, TEXT, bold=True)
    text(s, 8.75, yy + 0.29, 4.0, 0.42, b, 11.2, MUTED, line_spacing=1.25)
pill(s, 8.25, 6.17, 4.15, '15 种算法  ·  24 条短片  ·  1 个实时作业', 10, ACCENT)
notes(s, '这一页让同学先看到产品表面：推荐流、推荐理由、互动按钮。右下三个数字分别代表算法、内容和实时链路的规模。可以问：如果没有实时链路，这个页面会少什么？')

# ---------- 03 three questions ----------
s = slide_new()
header(s, '02  /  THE FRAME', '推荐系统，只回答三个问题', 3)
cols = [
    ('01', '用户是谁？', '历史行为、偏好强度、\n最近一次互动。'),
    ('02', '内容是什么？', '类别、标签、作者、\n以及它最近的热度。'),
    ('03', '下一次给什么？', '在相关性、时效性、\n多样性之间做取舍。'),
]
for i, (n, q, b) in enumerate(cols):
    x = 0.72 + i * 3.84
    text(s, x, 1.78, 3.2, 0.8, n, 48, RGBColor(0x4A,0x3E,0x62), bold=True, font=MONO, line_spacing=0.8)
    text(s, x, 2.54, 3.3, 0.55, q, 22, TEXT, bold=True)
    text(s, x, 3.22, 3.2, 0.9, b, 13, MUTED, line_spacing=1.5)
    if i < 2:
        line(s, x + 3.62, 2.05, x + 3.62, 5.25, LINE, 0.7)
text(s, 0.72, 4.92, 11.8, 0.24, 'USER  ×  ITEM  ×  CONTEXT   →   RANKING', 9.2, DIM, font=MONO, spacing=1.2)
text(s, 0.72, 5.55, 11.8, 0.34, '从「猜你喜欢」到「我懂你」：三问之间，是数据与计算的往返。', 12, LIGHT, italic=True)
notes(s, '把推荐系统压缩成三个问题：用户是谁、内容是什么、下一次给什么。可以让学生用自己刷短视频的经验各举一个例子，后面所有表、算法和实时链路都围绕这三问展开。')

# ---------- 04 architecture ----------
s = slide_new()
header(s, '03  /  ARCHITECTURE', '系统全景：一条行为，如何走完全程', 4)
cols = [
    ('交互层', 0.72, 2.55),
    ('服务层', 3.62, 2.40),
    ('数据层', 6.35, 2.40),
    ('实时层', 9.28, 3.32),
]
for name, x, w in cols:
    label(s, x, 1.62, w, name.upper(), ACCENT, 9.0, 2.0)
    line(s, x, 1.9, x + w - 0.15, 1.9, LINE, 0.6)
boxes = [
    (0.72, 2.08, 2.55, '浏览器 / 播放器', '登录 · 点赞 · 收藏 · 完播'),
    (0.72, 3.24, 2.55, '推荐界面', '混合推荐 · 推荐理由'),
    (0.72, 4.40, 2.55, '事件上报', 'POST /api/events'),
    (3.62, 2.08, 2.40, 'FastAPI', 'Auth · 推荐 · 事件'),
    (3.62, 3.24, 2.40, '推荐服务', '召回 · 排序 · 解释'),
    (3.62, 4.40, 2.40, '用户身份', 'Bearer 会话'),
    (6.35, 2.08, 2.40, 'MySQL 业务库', '用户 · 视频 · 互动'),
    (6.35, 3.24, 2.40, 'Outbox', '可靠投递 Kafka'),
    (6.35, 4.40, 2.40, 'stream_* 特征', '事件 · 特征 · 热度'),
    (9.28, 2.08, 3.32, 'Kafka', 'rec-events  ·  3 partitions'),
    (9.28, 3.24, 3.32, 'Flink SQL', 'watermark · dedupe · UDF'),
    (9.28, 4.40, 3.32, 'HDFS Checkpoint', '10s · EXACTLY_ONCE'),
]
for x, y, w, h, b in boxes:
    rect(s, x, y, w, 0.92, PANEL, LINE, 0.05)
    text(s, x + 0.16, y + 0.14, w - 0.28, 0.27, h, 12.5, TEXT, bold=True)
    text(s, x + 0.16, y + 0.49, w - 0.28, 0.28, b, 9.2, MUTED)
# only draw real flows, not a false linear pipeline
arrow(s, 3.29, 2.48, 0.28, 0.18)
arrow(s, 6.02, 2.48, 0.28, 0.18)
# Outbox -> Kafka, Flink -> stream_*: diagonal across the column gap
line_arrow(s, 8.80, 3.55, 9.24, 2.55)
line_arrow(s, 9.24, 3.72, 8.80, 4.82)
# Within the realtime layer
arrow_y = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(10.90), Inches(3.00), Inches(0.18), Inches(0.20))
arrow_y.shadow.inherit = False; arrow_y.fill.solid(); arrow_y.fill.fore_color.rgb = RGBColor(0x8A,0x75,0xC9); arrow_y.line.fill.background()
arrow_y2 = s.shapes.add_shape(MSO_SHAPE.DOWN_ARROW, Inches(10.90), Inches(4.16), Inches(0.18), Inches(0.20))
arrow_y2.shadow.inherit = False; arrow_y2.fill.solid(); arrow_y2.fill.fore_color.rgb = RGBColor(0x8A,0x75,0xC9); arrow_y2.line.fill.background()
text(s, 0.72, 5.63, 11.8, 0.5,
     '写入与计算解耦：业务事务只写 MySQL；Outbox 异步投递 Kafka；Flink 计算后回写 stream_* 表。',
     12.2, MUTED, line_spacing=1.3)
pill(s, 0.72, 6.25, 4.55, '一条行为：API → MySQL → Kafka → Flink → 特征表', 9.5, LIGHT)
notes(s, '这张图不要逐字念。强调三个边界：事务边界在 MySQL，投递边界在 Outbox 和 Kafka，计算边界在 Flink。推荐服务读特征表，不直接扫明细。可以问：如果 Kafka 挂了，业务还能不能写入？')

# ---------- 05 data model ----------
s = slide_new()
header(s, '04  /  DATA MODEL', '数据模型：明细、特征、窗口，各司其职', 5)
cards = [
    ('01  /  EVENT LOG', 'stream_events', ['event_id    PK', 'user_id', 'item_id', 'action', 'ts_ms'], '一条行为一行。\nevent_id 幂等，重复上报只算一次。', 'AUDIT', '幂等与追溯'),
    ('02  /  FEATURES', 'stream_user_item_features', ['user_id', 'item_id', 'preference', 'interactions', 'last_ts'], '用户 × 物品的绝对特征。\n直接服务排序与解释。', 'RANKING', '排序主特征'),
    ('03  /  WINDOW', 'stream_item_hotness', ['window_start', 'window_end', 'item_id', 'score'], '1 分钟 TUMBLE。\n回答：最近什么在升温？', 'EXPLAIN', '趋势解释'),
]
for i, (lab, name, fields, body, read_by, read_use) in enumerate(cards):
    x = 0.72 + i * 3.84
    rect(s, x, 1.62, 3.55, 4.45, PANEL, LINE, 0.045)
    rect(s, x + 0.22, 1.84, 0.34, 0.04, ACCENT, None, shape=MSO_SHAPE.RECTANGLE)
    text(s, x + 0.22, 1.98, 3.05, 0.24, lab, 8.8, ACCENT, bold=True, spacing=1.7)
    text(s, x + 0.22, 2.28, 3.1, 0.48, name, 12.8, TEXT, bold=True, font=MONO)
    fy = 2.9
    for f in fields:
        text(s, x + 0.22, fy, 3.1, 0.23, f, 10.2, RGBColor(0xC9,0xC0,0xD8), font=MONO)
        fy += 0.27
    text(s, x + 0.22, 4.56, 3.1, 0.2, 'READ BY  /  ' + read_by, 7.6, ACCENT, bold=True, spacing=1.3)
    text(s, x + 0.22, 4.78, 3.1, 0.2, read_use, 9.2, MUTED)
    line(s, x + 0.22, 5.28, x + 3.33, 5.28, LINE, 0.6)
    text(s, x + 0.22, 5.43, 3.1, 0.5, body, 9.4, MUTED, line_spacing=1.25)
# bottom flow
text(s, 0.72, 6.34, 2.2, 0.26, '明细', 10, ACCENT, bold=True)
arrow(s, 1.58, 6.35, 0.4, 0.18)
text(s, 2.15, 6.34, 2.4, 0.26, '聚合 / 窗口', 10, LIGHT, bold=True)
arrow(s, 3.75, 6.35, 0.4, 0.18)
text(s, 4.3, 6.34, 3.0, 0.26, '服务特征', 10, LIGHT, bold=True)
text(s, 7.6, 6.34, 4.9, 0.26, '所有表都由 Flink SQL 维护，推荐 API 只读特征。', 9.6, DIM)
notes(s, '三张表分别对应明细、特征、窗口。可以问：如果只有明细表，推荐服务每次请求要扫多少行？由此引出预聚合和窗口的必要性。')

# ---------- 06 recommendation path ----------
s = slide_new()
header(s, '05  /  RANKING PATH', '推荐路径：24 条候选，如何变成一屏结果', 6)
steps = [
    ('01', '候选池', '24 条本地短片\n先保证内容可控'),
    ('02', '多路召回', '热门 / 时效 / 内容\n协同 / 会话'),
    ('03', '融合排序', 'Hybrid：协同 + 内容\n+ 热度 + 探索'),
    ('04', '多样性重排', 'MMR：别让一屏\n都是同一种'),
]
outputs = ['输出  24 条候选', '输出  多路候选', '输出  排序分', '输出  最终 12 条']
for i, (n, h, b) in enumerate(steps):
    x = 0.72 + i * 3.13
    rect(s, x, 1.78, 2.78, 3.55, PANEL, LINE, 0.05)
    text(s, x + 0.2, 1.96, 0.5, 0.25, n, 10, ACCENT, bold=True, font=MONO)
    text(s, x + 0.2, 2.28, 2.35, 0.42, h, 18, TEXT, bold=True)
    text(s, x + 0.2, 2.9, 2.35, 0.9, b, 11.2, MUTED, line_spacing=1.45)
    line(s, x + 0.2, 4.62, x + 2.35, 4.62, LINE, 0.5)
    text(s, x + 0.2, 4.76, 2.35, 0.22, outputs[i], 8.6, ACCENT, font=MONO)
    if i < 3:
        arrow(s, x + 2.86, 3.28, 0.2, 0.16, RGBColor(0x5A,0x4B,0x73))
pill(s, 9.95, 1.52, 2.65, '15 种算法  ·  可解释', 9.2, LIGHT)
rect(s, 0.72, 5.42, 11.85, 1.05, PANEL2, RGBColor(0x3A,0x30,0x4D), 0.05)
text(s, 0.95, 5.58, 11.4, 0.3, 'score(u, i) = f( 协同信号, 内容相似, 实时热度, 探索 )', 15, LIGHT, font=MONO)
text(s, 0.95, 5.98, 11.4, 0.26, '融合不是简单加权，而是对「相关性、时效性、多样性」的取舍。', 9.2, MUTED)
notes(s, '这一页把推荐拆成四步：候选控制、信号覆盖、排序融合、体验多样性。重点不是算法名字，而是每一步在解决什么约束。可以追问：多样性重排会不会伤害相关性？')

# ---------- 07 batch vs stream ----------
s = slide_new()
header(s, '06  /  WHY STREAMING', '为什么要把计算搬到流上？', 7)
rect(s, 0.72, 1.65, 5.75, 3.95, PANEL, LINE, 0.05)
rect(s, 6.86, 1.65, 5.75, 3.95, RGBColor(0x20,0x1A,0x30), RGBColor(0x4A,0x3D,0x64), 0.05)
text(s, 0.98, 1.86, 3.0, 0.24, 'BATCH  /  T+1', 9.2, MUTED, bold=True, spacing=1.8)
text(s, 0.98, 2.18, 4.8, 0.46, '离线批处理', 22, TEXT, bold=True)
text(s, 7.12, 1.86, 3.8, 0.24, 'STREAM  /  SECONDS', 9.2, ACCENT, bold=True, spacing=1.8)
text(s, 7.12, 2.18, 4.8, 0.46, '实时流处理', 22, TEXT, bold=True)
left = ['全量重算，链路长', '行为要等到下一轮', '很难解释「刚刚」发生了什么']
right = ['增量更新，秒级可见', '窗口热度持续变化', '下一刷就能反映这次互动']
for i in range(3):
    text(s, 0.98, 3.02 + i * 0.64, 0.18, 0.2, '·', 18, DIM, bold=True)
    text(s, 1.18, 3.02 + i * 0.64, 4.9, 0.42, left[i], 12.5, MUTED)
    text(s, 7.12, 3.02 + i * 0.64, 0.18, 0.2, '·', 18, ACCENT, bold=True)
    text(s, 7.32, 3.02 + i * 0.64, 4.9, 0.42, right[i], 12.5, LIGHT)
# VS
circ = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(6.24), Inches(3.18), Inches(0.78), Inches(0.78))
circ.shadow.inherit = False; circ.fill.solid(); circ.fill.fore_color.rgb = BG
circ.line.color.rgb = ACCENT; circ.line.width = Pt(1.0)
text(s, 6.24, 3.40, 0.78, 0.28, 'VS', 10, ACCENT, bold=True, align=PP_ALIGN.CENTER, spacing=1.5)
text(s, 0.72, 5.93, 11.8, 0.4, '用户刚点过赞，下一刷就应该不一样。', 17, LIGHT, italic=True)
notes(s, '对比批处理和流处理，不要贬低批处理。批处理适合全量训练和回填，流处理适合把刚刚发生的行为变成下一刷的特征。两者是互补关系，可以问：哪些指标必须实时，哪些可以离线？')

# ---------- 08 pipeline ----------
s = slide_new()
header(s, '07  /  PIPELINE', 'Kafka → Flink SQL：一条 SQL 数据流水线', 8)
# source
rect(s, 0.72, 2.0, 2.42, 1.55, PANEL, LINE, 0.05)
text(s, 0.92, 2.16, 2.0, 0.26, 'KAFKA TOPIC', 8.8, ACCENT, bold=True, spacing=1.5)
text(s, 0.92, 2.48, 2.0, 0.34, 'rec-events', 16, TEXT, bold=True, font=MONO)
text(s, 0.92, 2.92, 2.0, 0.4, '3 partitions\n9 种行为', 9.5, MUTED, line_spacing=1.2)
arrow(s, 3.18, 2.68, 0.28, 0.2)
# source table
rect(s, 3.56, 2.0, 2.55, 1.55, PANEL, LINE, 0.05)
text(s, 3.76, 2.16, 2.2, 0.26, 'SQL SOURCE TABLE', 8.8, ACCENT, bold=True, spacing=1.5)
text(s, 3.76, 2.48, 2.2, 0.34, 'kafka_events', 15, TEXT, bold=True, font=MONO)
text(s, 3.76, 2.92, 2.15, 0.4, 'event_time + WATERMARK\n5 秒乱序容忍', 9.2, MUTED, line_spacing=1.2)
arrow(s, 6.16, 2.68, 0.28, 0.2)
# views
rect(s, 6.54, 1.78, 2.55, 2.05, RGBColor(0x20,0x1A,0x30), RGBColor(0x4A,0x3D,0x64), 0.05)
text(s, 6.74, 1.92, 2.2, 0.24, 'LOGICAL VIEWS', 8.8, LIGHT, bold=True, spacing=1.5)
text(s, 6.74, 2.24, 2.25, 0.3, 'valid_events', 12.5, TEXT, bold=True, font=MONO)
text(s, 6.74, 2.55, 2.25, 0.24, '↓  ROW_NUMBER()', 9.5, ACCENT, font=MONO)
text(s, 6.74, 2.84, 2.25, 0.3, 'unique_events', 12.5, TEXT, bold=True, font=MONO)
text(s, 6.74, 3.25, 2.25, 0.4, '按 event_id 去重\n再进入聚合', 9.2, MUTED, line_spacing=1.2)
# sinks
sink_y = [1.74, 3.02, 4.30]
sink_names = [('stream_events', '行为明细 · 权重'), ('stream_user_item_features', '用户 × 物品特征'), ('stream_item_hotness', '1 分钟窗口热度')]
for (nm, sub), yy in zip(sink_names, sink_y):
    rect(s, 9.66, yy, 2.95, 0.98, PANEL, LINE, 0.05)
    text(s, 9.84, yy + 0.14, 2.6, 0.26, nm, 11.2, TEXT, bold=True, font=MONO)
    text(s, 9.84, yy + 0.48, 2.6, 0.22, sub, 8.8, MUTED)
# fan-out: a single vertical rail from views, then three short arrows
line(s, 9.24, 2.25, 9.24, 4.76, RGBColor(0x5F,0x50,0x7A), 0.8)
for yy in sink_y:
    line(s, 9.24, yy + 0.49, 9.58, yy + 0.49, RGBColor(0x5F,0x50,0x7A), 0.8)
    arrow(s, 9.28, yy + 0.40, 0.26, 0.18, RGBColor(0x8A,0x75,0xC9))
# connector label
text(s, 3.76, 1.62, 2.2, 0.22, 'source', 8.2, DIM, font=MONO)
text(s, 6.74, 1.62, 2.2, 0.22, 'dedupe', 8.2, DIM, font=MONO)
text(s, 9.66, 1.52, 2.0, 0.22, 'SINK TABLES', 8.2, DIM, font=MONO)
# bottom facts
facts = [('row_number', '同一 event_id 只算一次'), ('TUMBLE(1 min)', '窗口热度持续更新'), ('1 STATEMENT SET', '3 个 INSERT，1 个 Job')]
for i, (a, b) in enumerate(facts):
    x = 0.72 + i * 4.0
    rect(s, x, 5.78, 3.72, 0.72, PANEL, LINE, 0.06)
    text(s, x + 0.16, 5.9, 3.4, 0.22, a, 9.5, ACCENT, bold=True, font=MONO)
    text(s, x + 0.16, 6.13, 3.4, 0.2, b, 8.8, MUTED)
notes(s, '这条链路的关键是「先清洗、再去重、再聚合」。Kafka 负责缓冲，Flink 负责口径，MySQL 特征表服务读取。可以问：为什么不在 API 里直接算？')

# ---------- 09 SQL ----------
s = slide_new()
header(s, '08  /  SQL IS THE INTERFACE', 'SQL 是主角：把口径写进查询', 9)
rect(s, 0.72, 1.62, 7.42, 5.26, RGBColor(0x12,0x10,0x19), RGBColor(0x35,0x2C,0x45), 0.04)
code_lines = [
    ('-- 1. 事件时间与乱序容忍', DIM),
    ('CREATE TABLE kafka_events (', LIGHT),
    ('  event_id STRING, user_id STRING,', TEXT),
    ('  item_id STRING, action STRING, ts_ms BIGINT,', TEXT),
    ('  event_time AS TO_TIMESTAMP_LTZ(ts_ms, 3),', TEXT),
    ('  WATERMARK FOR event_time', ACCENT),
    ('    AS event_time - INTERVAL \'5\' SECOND', ACCENT),
    (') WITH ( \'connector\' = \'kafka\', ... );', TEXT),
    ('', TEXT),
    ('-- 2. 幂等：同一 event_id 只保留一条', DIM),
    ('SELECT * FROM (', LIGHT),
    ('  SELECT *, ROW_NUMBER() OVER (', TEXT),
    ('    PARTITION BY event_id ORDER BY proc_time) rn', TEXT),
    ('  FROM valid_events', TEXT),
    (') WHERE rn = 1;', TEXT),
    ('', TEXT),
    ('-- 3. 三个 INSERT 收进一个作业', DIM),
    ('EXECUTE STATEMENT SET BEGIN', ACCENT),
    ('  INSERT INTO stream_events ...;', TEXT),
    ('  INSERT INTO stream_user_item_features ...;', TEXT),
    ('  INSERT INTO stream_item_hotness ...;', TEXT),
    ('END;', ACCENT),
]
yy = 1.82
for ln, col in code_lines:
    text(s, 0.96, yy, 7.0, 0.2, ln, 8.5, col, font=MONO, line_spacing=1.0)
    yy += 0.218
notes(s, '这一页只讲三个点：事件时间、幂等去重、Statement Set。SQL 不是胶水，它定义了实时特征的口径。可以让学生找一下：哪一行保证重复事件不重复计分？')
# right notes
notes_items = [
    ('01', '事件时间', '用 ts_ms 生成 event_time，5 秒 watermark 容忍乱序。'),
    ('02', '先去重', 'event_id 是幂等键；重复上报不能重复计分。'),
    ('03', '一次提交', '3 个 INSERT 放进一个 Statement Set，只有一个 Job ID。'),
]
for i, (n, h, b) in enumerate(notes_items):
    yy = 1.78 + i * 1.62
    text(s, 8.55, yy, 0.38, 0.24, n, 9.5, ACCENT, bold=True, font=MONO)
    text(s, 8.98, yy - 0.03, 3.7, 0.3, h, 14, TEXT, bold=True)
    text(s, 8.98, yy + 0.3, 3.7, 0.62, b, 10.5, MUTED, line_spacing=1.35)
text(s, 8.55, 6.55, 3.9, 0.22, 'infra/flink/pipeline.sql', 8.6, DIM, font=MONO)

# ---------- 10 UDF ----------
s = slide_new()
header(s, '09  /  BUSINESS LOGIC', '把业务权重写进 Python UDF', 10)
# weight table
rect(s, 0.72, 1.62, 5.45, 4.92, PANEL, LINE, 0.04)
text(s, 0.94, 1.78, 2.0, 0.24, 'POSITIVE', 8.8, ACCENT, bold=True, spacing=1.6)
text(s, 3.58, 1.78, 2.0, 0.24, 'NEGATIVE', 8.8, ACCENT, bold=True, spacing=1.6)
line(s, 3.34, 2.12, 3.34, 4.28, LINE, 0.6)
pos = [('view', '0.2'), ('complete', '1.0'), ('like', '3.0'), ('favorite', '4.0'), ('follow', '2.0')]
neg = [('unlike', '-3.0'), ('unfavorite', '-4.0'), ('unfollow', '-2.0'), ('skip', '-0.5')]
for i, (a, v) in enumerate(pos):
    y = 2.18 + i * 0.40
    text(s, 0.94, y, 1.25, 0.24, a, 9.8, TEXT, font=MONO)
    text(s, 2.03, y - 0.03, 0.95, 0.28, v, 11.8, GREEN, bold=True, font=MONO, align=PP_ALIGN.RIGHT)
for i, (a, v) in enumerate(neg):
    y = 2.18 + i * 0.40
    text(s, 3.58, y, 1.25, 0.24, a, 9.8, TEXT, font=MONO)
    text(s, 4.67, y - 0.03, 0.95, 0.28, v, 11.8, CORAL, bold=True, font=MONO, align=PP_ALIGN.RIGHT)
# guidance
line(s, 0.94, 4.52, 5.95, 4.52, LINE, 0.6)
text(s, 0.94, 4.68, 4.95, 0.6, '9 种行为，正负分。\n权重是产品语言，不是模型参数。', 9.2, MUTED, line_spacing=1.4)
text(s, 0.94, 5.48, 4.95, 0.22, '可解释  /  可回滚  /  可做 A/B', 8.8, ACCENT, bold=True, spacing=1.2)
# right formula
rect(s, 6.55, 1.62, 5.95, 2.02, RGBColor(0x20,0x1A,0x30), RGBColor(0x4A,0x3D,0x64), 0.05)
text(s, 6.78, 1.76, 4.5, 0.24, 'DECAY  /  24 HOURS', 8.8, ACCENT, bold=True, spacing=1.6)
text(s, 6.78, 2.04, 5.4, 0.42, 'weight × exp(-Δh / 24)', 22, LIGHT, font=MONO)
text(s, 6.78, 2.56, 5.4, 0.26, '越久远的行为，权重越低；但不会瞬间归零。', 10, MUTED)
# code
rect(s, 6.55, 3.82, 5.95, 2.72, RGBColor(0x12,0x10,0x19), RGBColor(0x35,0x2C,0x45), 0.04)
code = [
    ("@udf(result_type='DOUBLE')", ACCENT),
    ('def behavior_weight(action):', LIGHT),
    ('    return WEIGHTS.get(action, 0.0)', TEXT),
    ('', TEXT),
    ("@udf(result_type='DOUBLE')", ACCENT),
    ('def time_decay(weight, hours):', LIGHT),
    ('    return weight * math.exp(-hours / 24)', TEXT),
]
yy = 3.98
for ln, col in code:
    text(s, 6.76, yy, 5.5, 0.22, ln, 9.2, col, font=MONO)
    yy += 0.25
text(s, 0.72, 6.72, 7.6, 0.22, 'SQL 里只写 behavior_weight(action)，规则集中在 Python。', 9.2, DIM)
notes(s, 'UDF 的意义是把产品规则从 SQL 里抽出来，但不能抽得太远。权重表要可读、可改、可测试，衰减函数要能解释。可以问：权重应该由产品定，还是由模型学？')

# ---------- 11 checkpoint ----------
s = slide_new()
header(s, '10  /  RECOVERY', '可恢复，才敢实时', 11)
cards = [
    ('01', 'CHECKPOINT', '10 秒一次', 'EXACTLY_ONCE\nRETAIN_ON_CANCELLATION\n状态后端：hashmap'),
    ('02', 'SAVEPOINT', '升级前的手动存档', '停止作业前保存\nSET execution.savepoint.path\n再提交，从断点继续'),
    ('03', 'ONE JOB', '一个作业，一个 ID', '3 个 INSERT\nEXECUTE STATEMENT SET\n统一恢复路径'),
]
for i, (n, lab, h, b) in enumerate(cards):
    x = 0.72 + i * 3.84
    rect(s, x, 1.66, 3.55, 3.55, PANEL, LINE, 0.05)
    text(s, x + 0.22, 1.84, 0.5, 0.24, n, 9.5, ACCENT, bold=True, font=MONO)
    text(s, x + 0.22, 2.14, 3.0, 0.24, lab, 8.8, ACCENT, bold=True, spacing=1.7)
    text(s, x + 0.22, 2.44, 3.0, 0.4, h, 18, TEXT, bold=True)
    text(s, x + 0.22, 3.05, 3.0, 1.3, b, 10, MUTED, line_spacing=1.55)
# bottom flow
flow = [('Kafka', 0.72, 1.55), ('Flink state', 2.65, 1.9), ('Checkpoint', 4.95, 1.9), ('HDFS', 7.25, 1.4)]
for name, x, w in flow:
    rect(s, x, 5.62, w, 0.62, PANEL2, LINE, 0.1)
    text(s, x, 5.79, w, 0.24, name, 9.8, LIGHT, bold=True, align=PP_ALIGN.CENTER)
for x in (2.28, 4.58, 6.88):
    arrow(s, x, 5.82, 0.3, 0.18)
text(s, 9.0, 5.72, 3.6, 0.4, '最近验证：chk-11\nHDFS · 0 未处理异常', 9.2, MUTED, line_spacing=1.35)
text(s, 0.72, 6.52, 7.8, 0.22, '实时系统的不确定性，要用可恢复性来兜底。', 9.5, DIM)
notes(s, '这部分最容易被忽略，但工程上最重要。checkpoint 管自动恢复，savepoint 管主动升级，一个 Statement Set 让恢复路径也保持单一。可以问：如果没有 savepoint，升级会丢什么？')

# ---------- 12 validation ----------
s = slide_new()
header(s, '11  /  EVIDENCE', '验证：用数字说明它真的在工作', 12)
stats = [('79', 'tests passed', 'pytest backend/tests', ACCENT),
         ('24', 'unique videos', '24 个唯一标题 / URL', LIGHT),
         ('15', 'algorithms', '经典推荐基线', LIGHT),
         ('1', 'running job', '3 个 INSERT 的 Statement Set', GREEN)]
for i, (v, u, c, col) in enumerate(stats):
    x = 0.72 + i * 3.02
    rect(s, x, 1.62, 2.72, 1.48, PANEL, LINE, 0.05)
    stat(s, x + 0.18, 1.76, 2.3, v, u, c, col)
# two panels
rect(s, 0.72, 3.45, 6.0, 3.05, PANEL, LINE, 0.045)
rect(s, 6.95, 3.45, 5.55, 3.05, PANEL, LINE, 0.045)
text(s, 0.96, 3.62, 5.0, 0.24, '验证路径', 10, ACCENT, bold=True, spacing=1.6)
text(s, 7.18, 3.62, 5.0, 0.24, '工程教训', 10, ACCENT, bold=True, spacing=1.6)
checks = ['SQL Client 提交：1 个 Job，5 个顶点 RUNNING', '实时事件写入 stream_events，特征聚合对账一致', 'Range 请求返回 206，视频可拖动播放']
lessons = ['环境没有 YARN：改用 standalone SQL Client', '裸 STATEMENT SET 不支持：改用 EXECUTE', '重复 seed 不更新：加 repair 路径']
for i, t in enumerate(checks):
    text(s, 0.96, 4.02 + i * 0.62, 5.4, 0.45, '·  ' + t, 9.8, MUTED, line_spacing=1.3)
for i, t in enumerate(lessons):
    text(s, 7.18, 4.02 + i * 0.62, 5.0, 0.45, '·  ' + t, 9.8, MUTED, line_spacing=1.3)
notes(s, '数字不是为了炫技，而是证明链路闭环。79 个测试覆盖业务、认证、媒体、SQL 渲染；24 条唯一视频保证目录没有重复；1 个实时作业说明 Statement Set 生效。')

# ---------- 13 discussion ----------
s = slide_new()
header(s, '12  /  DISCUSSION', '课堂讨论：如果换你来设计', 13)
qs = [
    ('01', '冷启动', '一个新用户没有任何行为，\n第一屏推荐什么？'),
    ('02', '重复事件', '同一次点击被上报两次，\n应该在哪里去重？'),
    ('03', '窗口延迟', '数据晚到 30 秒，\n热度还准吗？'),
]
for i, (n, h, b) in enumerate(qs):
    x = 0.72 + i * 3.84
    text(s, x, 1.75, 0.5, 0.26, n, 10, ACCENT, bold=True, font=MONO)
    text(s, x, 2.08, 3.3, 0.42, h, 22, TEXT, bold=True)
    text(s, x, 2.68, 3.25, 0.9, b, 12.5, MUTED, line_spacing=1.5)
    if i < 2:
        line(s, x + 3.6, 2.0, x + 3.6, 4.55, LINE, 0.7)
rect(s, 0.72, 4.78, 11.85, 1.15, RGBColor(0x20,0x1A,0x30), RGBColor(0x4A,0x3D,0x64), 0.05)
text(s, 0.98, 4.98, 11.2, 0.4, '没有标准答案，只有可验证的取舍。', 18, LIGHT, italic=True)
text(s, 0.98, 5.42, 11.2, 0.26, '把选择写进 SQL，把假设写进测试。', 10.5, MUTED)
notes(s, '讨论题没有标准答案。引导学生从产品、数据、工程三个角度回答，并追问：你怎么验证自己的选择？可以分组讨论 5 分钟。')

# ---------- 14 closing ----------
s = slide_new()
# subtle accent glow shape
rect(s, 0.0, 0.0, 0.18, 7.5, RGBColor(0x2B,0x23,0x3D), None, shape=MSO_SHAPE.RECTANGLE)
label(s, 0.82, 0.62, 6.0, 'THANK YOU  /  Q & A')
text(s, 0.82, 1.05, 7.4, 1.0, '把复杂留给系统，', 34, TEXT, bold=True, line_spacing=1.05)
text(s, 0.82, 1.72, 7.4, 1.0, '把简单留给用户。', 34, LIGHT, bold=True, line_spacing=1.05)
text(s, 0.84, 2.98, 6.5, 0.8, '映刻 YINGKE\n短视频推荐系统 · 课堂分享', 13, MUTED, line_spacing=1.5)
line(s, 0.84, 4.15, 6.2, 4.15, LINE, 0.7)
takeaways = [('01', '推荐是一个回路', '行为 → 特征 → 排序 → 下一次行为'),
             ('02', '实时是口径问题', '窗口、去重、水位线，比框架更重要'),
             ('03', '可恢复才可运营', 'checkpoint / savepoint / 单一 Job ID')]
for i, (n, h, b) in enumerate(takeaways):
    yy = 4.38 + i * 0.68
    text(s, 0.84, yy, 0.42, 0.22, n, 8.8, ACCENT, bold=True, font=MONO)
    text(s, 1.3, yy - 0.02, 4.6, 0.26, h, 12.5, TEXT, bold=True)
    text(s, 1.3, yy + 0.25, 5.0, 0.24, b, 9.5, MUTED)
# right panel
rect(s, 8.25, 1.1, 4.25, 5.55, PANEL, LINE, 0.05)
text(s, 8.5, 1.35, 3.7, 0.26, 'ONE MORE THING', 8.8, ACCENT, bold=True, spacing=1.8)
text(s, 8.5, 1.72, 3.6, 0.9, '问题比\n答案更重要。', 26, LIGHT, bold=True, line_spacing=1.12)
text(s, 8.5, 3.02, 3.6, 1.0, '课后可以继续追问：\n如果换成多模态内容？\n如果延迟再低 10 倍？', 10.5, MUTED, line_spacing=1.55)
text(s, 8.5, 5.85, 3.6, 0.24, '映刻  /  YINGKE', 9, DIM, font=MONO)
notes(s, '收尾用三句话总结：推荐是回路，实时是口径，可恢复才可运营。最后把问题留给同学：如果条件变化，你的设计会怎么变？')

# ---------- save + inspect ----------
prs.save(OUT)
print('saved', OUT, OUT.stat().st_size, 'slides', len(prs.slides))
for i, s in enumerate(prs.slides, 1):
    print(i, 'shapes', len(s.shapes), 'notes', bool(s.notes_slide.notes_text_frame.text))
