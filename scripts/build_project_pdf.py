"""Build the optional project guide PDF (requires reportlab and a Chinese TTF/TTC font)."""
import argparse
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, PageBreak,
    Table, TableStyle, Flowable, KeepTogether,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
NAVY = colors.HexColor('#13283E')
BLUE = colors.HexColor('#166B91')
TEAL = colors.HexColor('#00867D')
INK = colors.HexColor('#25364A')
GRAY = colors.HexColor('#66798C')
PALE = colors.HexColor('#F0F5F8')
WIDTH = A4[0] - 100


class Cover(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = WIDTH, 670

    def draw(self):
        c = self.canv
        c.setFillColor(NAVY)
        c.roundRect(0, 85, self.width, 550, 14, fill=1, stroke=0)
        c.setFillColor(colors.HexColor('#52CFBF'))
        c.rect(28, 585, 48, 5, fill=1, stroke=0)
        c.setFont('GuideBold', 39)
        c.setFillColor(colors.white)
        c.drawString(28, 516, 'CodeRoute')
        c.setFont('GuideBold', 24)
        c.drawString(28, 465, '项目设计与实现详解')
        c.setFont('Guide', 13)
        c.setFillColor(colors.HexColor('#CBDFEB'))
        c.drawString(28, 427, '基于自适应 Harness 的多智能体代码修复系统')
        for y, line in [(353, '分析代码 / 修改补丁 / 执行测试'),
                        (324, '动态路由 / 失败诊断 / 审查与独立验收')]:
            c.drawString(28, y, line)
        for x, value, label in [(28, '5', '协作角色'), (179, '13 / 14', '固定评测成功'), (334, '124', '工程测试通过')]:
            c.setFillColor(colors.white)
            c.setFont('GuideBold', 25)
            c.drawString(x, 235, value)
            c.setFillColor(colors.HexColor('#CBDFEB'))
            c.setFont('Guide', 10)
            c.drawString(x, 211, label)
        c.setFont('Guide', 10)
        c.drawString(28, 140, 'Python + pytest | DeepSeek + OpenRouter Qwen')
        c.setFillColor(GRAY)
        c.drawString(0, 40, '第一版交付说明  ·  版本 0.1.0  ·  2026-09-29')
        c.setFont('Guide', 9)
        c.drawString(0, 18, '含架构、核心机制、代码导读、使用方法、评测与失败分析')


class Architecture(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = WIDTH, 215

    def draw(self):
        c = self.canv
        boxes = [(136, 168, 220, 'Harness + Shared State', NAVY),
                 (136, 115, 220, 'Router：规则 / 轻量 / 主模型', BLUE),
                 (10, 55, 140, 'Agent：执行局部任务', TEAL),
                 (176, 55, 140, 'Tools：文件 / pytest', TEAL),
                 (342, 55, 140, 'Tracing：轨迹与用量', TEAL)]
        for x, y, w, label, color in boxes:
            c.setFillColor(color)
            c.roundRect(x, y, w, 35, 5, fill=1, stroke=0)
            c.setFillColor(colors.white)
            c.setFont('Guide', 9)
            c.drawCentredString(x+w/2, y+13, label)
        c.setStrokeColor(GRAY)
        c.setLineWidth(1)
        for x1,y1,x2,y2 in [(246,168,246,150),(246,115,80,90),(246,115,246,90),(246,115,412,90)]:
            c.line(x1,y1,x2,y2)
        c.setFillColor(GRAY)
        c.setFont('Guide', 9)
        c.drawCentredString(WIDTH/2, 23, '执行结果更新共享状态，再由 Router 决定下一步')


class GuideDoc(BaseDocTemplate):
    chapter = ''

    def afterFlowable(self, flowable):
        if (isinstance(flowable, Paragraph) and flowable.style.name == 'Chapter'
                and re.match(r'^\d{2} ', flowable.getPlainText())):
            text = flowable.getPlainText()
            self.chapter = text
            key = 'chapter-' + text.split()[0]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text, key, level=0)
            self.notify('TOCEntry', (0, text, self.page, key))


def footer(canvas, doc):
    if doc.page == 1:
        return
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor('#DCE5EB'))
    canvas.line(50, A4[1]-43, A4[0]-50, A4[1]-43)
    canvas.line(50, 43, A4[0]-50, 43)
    canvas.setFont('Guide', 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(50, A4[1]-33, 'CODEROUTE  /  项目设计与实现')
    canvas.drawString(50, 29, 'Python · Multi-Agent · Adaptive Routing')
    canvas.drawRightString(A4[0]-50, 29, f'{doc.page:02d}')
    canvas.restoreState()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font', default='C:/Windows/Fonts/msyh.ttc')
    parser.add_argument('--bold-font', default='C:/Windows/Fonts/msyhbd.ttc')
    parser.add_argument('--output', default=str(ROOT/'output/pdf/CodeRoute_Project_Guide.pdf'))
    args = parser.parse_args()
    if not Path(args.font).is_file():
        parser.error('Provide a Chinese TrueType font via --font and --bold-font')
    pdfmetrics.registerFont(TTFont('Guide', args.font))
    pdfmetrics.registerFont(TTFont('GuideBold', args.bold_font if Path(args.bold_font).is_file() else args.font))
    styles = {
        'body': ParagraphStyle('Body', fontName='Guide', fontSize=10, leading=17,
            textColor=INK, wordWrap='CJK', spaceAfter=11),
        'chapter': ParagraphStyle('Chapter', fontName='GuideBold', fontSize=21, leading=31,
            textColor=NAVY, spaceAfter=20, keepWithNext=True, wordWrap='CJK'),
        'cell': ParagraphStyle('Cell', fontName='Guide', fontSize=8.7, leading=13.5,
            textColor=INK, wordWrap='CJK'),
        'head': ParagraphStyle('Head', fontName='GuideBold', fontSize=8.7, leading=13.5,
            textColor=colors.white, wordWrap='CJK'),
        'code': ParagraphStyle('Code', fontName='Guide', fontSize=8, leading=12,
            textColor=INK, wordWrap='CJK'),
    }
    story = [Cover(), PageBreak(), Paragraph('阅读导航', styles['chapter'])]
    story.append(Paragraph('从整体设计到实现细节，再到运行、评测与发布。目录和左侧书签均可点击跳转。', styles['body']))
    toc = TableOfContents()
    toc.levelStyles = [ParagraphStyle('Contents', fontName='Guide', fontSize=10, leading=24,
                                     textColor=INK, leftIndent=0, firstLineIndent=0)]
    story += [toc, PageBreak()]
    lines = (ROOT/'docs/PROJECT_GUIDE.md').read_text(encoding='utf-8').splitlines()
    i = 0
    started = False
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('## '):
            if started:
                story.append(PageBreak())
            started = True
            story.append(Paragraph(escape(line[3:]), styles['chapter']))
            i += 1
        elif not started or not line:
            i += 1
        elif line == '[ARCHITECTURE]':
            story.extend([Architecture(), Spacer(1, 9)])
            i += 1
        elif line.startswith('```'):
            is_diagram = line == '```mermaid'
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                code.append(lines[i]); i += 1
            if is_diagram:
                story.extend([Architecture(), Spacer(1, 9)])
                i += 1
                continue
            paragraph = Paragraph('<br/>'.join(escape(s).replace(' ', '&#160;') or '&#160;' for s in code), styles['code'])
            table = Table([[paragraph]], colWidths=[WIDTH])
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),
                ('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),
                ('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
            story += [table, Spacer(1,12)]
            i += 1
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                parts = [x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', p) for p in parts):
                    rows.append(parts)
                i += 1
            count = len(rows[0])
            proportions = {2:[0.32,0.68],3:[0.24,0.34,0.42],4:[0.43,0.18,0.19,0.20]}[count]
            cells = [[Paragraph(escape(t), styles['head' if n==0 else 'cell']) for t in row] for n,row in enumerate(rows)]
            table = Table(cells, colWidths=[WIDTH*p for p in proportions], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[PALE,colors.white]),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),
                ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
                ('LINEBELOW',(0,-1),(-1,-1),0.5,colors.HexColor('#DCE5EB'))]))
            story += [table, Spacer(1,14)]
        else:
            story.append(Paragraph(escape(line), styles['body']))
            i += 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = GuideDoc(str(output), pagesize=A4, leftMargin=50, rightMargin=50,
                   topMargin=65, bottomMargin=58, title='CodeRoute 项目设计与实现详解',
                   author='CodeRoute', subject='多智能体代码修复系统：架构、实现、使用与评测')
    doc.addPageTemplates(PageTemplate(id='guide', frames=[Frame(50,58,WIDTH,A4[1]-123,
                                    leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)], onPage=footer))
    doc.multiBuild(story)
    print(f'Created {output}')


if __name__ == '__main__':
    main()
