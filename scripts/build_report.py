"""Dựng báo cáo DOCX và tùy chọn xuất PDF bằng LibreOffice."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from src.knowledge import DATA_DIR, KB_DIR, OUTPUTS, ROOT, load_knowledge
from src.presentation import pct, signed, vi

REPORT = OUTPUTS / "report"
EXPERIMENTS = OUTPUTS / "experiments"
SCREENSHOTS = OUTPUTS / "screenshots"
NAME = "bao_cao_dinh_gia_xe_cu"
FONT = "Times New Roman"
NAVY = "153B66"
TITLE = "Hệ hỗ trợ quyết định dựa trên tri thức cho định giá xe ô tô cũ tại thị trường Việt Nam"

CONTENTS = [
    ("Mở đầu", 5, 0), ("Chương 1. Bài toán và cơ sở lý thuyết", 6, 0),
    ("Chương 2. Thiết kế hệ thống", 7, 0), ("2.1 Kiến trúc và cơ sở tri thức", 7, 1),
    ("2.2 Truy hồi và hiệu chỉnh tình huống", 8, 1), ("2.3 Tổng hợp giá, khoảng và độ tin cậy", 9, 1),
    ("Chương 3. Cài đặt và giao diện", 10, 0), ("3.1 Cài đặt và sơ đồ xử lý", 10, 1),
    ("3.2 Định giá và xem kết quả", 11, 1), ("3.3 Giải thích giá", 12, 1),
    ("3.4 Vết suy diễn", 13, 1), ("3.5 Xe tương tự", 14, 1),
    ("3.6 Phân tích dữ liệu", 15, 1), ("3.7 Quản trị tri thức", 16, 1),
    ("3.8 Cảnh báo lịch sử", 17, 1), ("3.9 Ca Vios từ giá mới đến độ tương tự", 18, 1),
    ("3.10 Ca Vios từ giá CBR đến khoảng đề xuất", 19, 1),
    ("Chương 4. Dữ liệu và thực nghiệm", 20, 0), ("4.1 Dữ liệu, làm sạch và phân chia", 20, 1),
    ("4.2 Kết quả bốn phương pháp", 21, 1), ("4.3 Khoảng giá hệ lai", 22, 1),
    ("4.4 Kiểm thử và giới hạn", 23, 1), ("Kết luận và hướng phát triển", 24, 0),
    ("Tài liệu tham khảo", 24, 0),
]

FIGURES = {
    "3.1": ("Biểu mẫu ca Vios trước khi định giá", 11, "01_form_nhap_xe.png"),
    "3.2": ("Giá đề xuất và hai đầu mút của khoảng", 11, "02_ket_qua_va_khoang_gia.png"),
    "3.3": ("Trọng số và phép tổng hợp giá", 12, "03_giai_thich_gia.png"),
    "3.4": ("Waterfall và vết suy diễn của Vios", 13, "04_vet_suy_dien.png"),
    "3.5": ("Năm tình huống truy hồi cho Vios", 14, "05_xe_tuong_tu.png"),
    "3.6": ("Phân tích kho tình huống train", 15, "06_phan_tich_du_lieu.png"),
    "3.7": ("Quản trị cơ sở tri thức", 16, "07_quan_tri_tri_thuc.png"),
    "3.8": ("Cảnh báo cho mẫu xe từng ngập nước", 17, "08_canh_bao_ngap_nuoc.png"),
    "4.1": ("MAE và MAPE trên phần test chung", 21, "errors.png"),
    "4.2": ("Minh họa khoảng đề xuất của hệ lai", 22, "intervals.png"),
}
TABLES = {
    "2.1": ("Các nhóm trong tập luật", 7), "2.2": ("Thuộc tính và trọng số CBR", 8),
    "3.1": ("Phép tính của từng luật cho ca Vios", 18), "3.2": ("Giá hiệu chỉnh và điểm tương tự", 19),
    "4.1": ("Nhật ký làm sạch dữ liệu", 20), "4.2": ("Sai số trên phần test chung và thời gian", 21),
    "4.3": ("Một số kiểm thử trên ứng dụng", 23),
}


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def set_style(style, *, size=13, bold=False, color="192739"):
    style.font.name = FONT
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor.from_string(color)
    properties = style.element.get_or_add_rPr()
    fonts = properties.rFonts
    for attribute in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme", "csTheme"):
        fonts.attrib.pop(qn(f"w:{attribute}"), None)
    for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attribute}"), FONT)
    language = properties.find(qn("w:lang"))
    if language is None:
        language = OxmlElement("w:lang")
        properties.append(language)
    language.set(qn("w:val"), "vi-VN")


def shade(cell, fill):
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shading)


class Report:
    def __init__(self):
        self.doc = Document()
        self.doc.core_properties.title = TITLE
        self.doc.core_properties.author = "Nhóm 4 · Đại học Công nghiệp Hà Nội"
        section = self.doc.sections[0]
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        section.top_margin = section.bottom_margin = section.right_margin = Cm(2)
        section.left_margin = Cm(3)
        section.header_distance, section.footer_distance = Cm(.85), Cm(.85)
        section.different_first_page_header_footer = True
        for style in self.doc.styles:
            if style.type in (WD_STYLE_TYPE.PARAGRAPH, WD_STYLE_TYPE.CHARACTER):
                set_style(style)
        normal = self.doc.styles["Normal"]
        normal.paragraph_format.line_spacing = 1.3
        normal.paragraph_format.space_after = Pt(5)
        normal.paragraph_format.widow_control = True
        normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for name, size in [("Title", 22), ("Heading 1", 17), ("Heading 2", 14), ("Heading 3", 13)]:
            style = self.doc.styles[name]
            set_style(style, size=size, bold=True, color=NAVY)
            style.paragraph_format.space_before = Pt(7)
            style.paragraph_format.space_after = Pt(5)
            style.paragraph_format.line_spacing = 1.3
            style.paragraph_format.keep_with_next = True
        for name, color in [("Report Caption", NAVY), ("Report Table", "192739"), ("Report Index", "192739")]:
            style = self.doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
            style.base_style = normal
            set_style(style, color=color)
            style.paragraph_format.line_spacing = 1.3
            style.paragraph_format.space_after = Pt(2)
            style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT

        header = section.header.paragraphs[0]
        header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = header.add_run("Công nghệ tri thức · Nhóm 4")
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor.from_string("536780")
        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        number = OxmlElement("w:fldSimple")
        number.set(qn("w:instr"), "PAGE")
        footer._p.append(number)

    def heading(self, title, level=1, *, page=False):
        paragraph = self.doc.add_heading(title, level=level)
        paragraph.paragraph_format.page_break_before = page
        return paragraph

    def body(self, text):
        paragraph = self.doc.add_paragraph(text)
        paragraph.paragraph_format.first_line_indent = Cm(.65)
        return paragraph

    def centered(self, text, *, bold=False, size=13, space=5):
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(space)
        run = paragraph.add_run(text)
        run.bold, run.font.size = bold, Pt(size)
        return paragraph

    def equation(self, text):
        paragraph = self.doc.add_paragraph()
        paragraph.paragraph_format.left_indent = Cm(.6)
        paragraph.paragraph_format.right_indent = Cm(.3)
        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = paragraph.add_run(text)
        run.bold = True
        run.font.color.rgb = RGBColor.from_string(NAVY)
        return paragraph

    def index(self, text, page, indent=0):
        paragraph = self.doc.add_paragraph(style="Report Index")
        paragraph.paragraph_format.left_indent = Cm(.66 * indent)
        paragraph.paragraph_format.tab_stops.add_tab_stop(Cm(15.95), WD_TAB_ALIGNMENT.RIGHT, WD_TAB_LEADER.DOTS)
        paragraph.add_run(f"{text}\t{page}")

    def table(self, headers, rows, widths, tag=None):
        if tag:
            caption = self.doc.add_paragraph(f"Bảng {tag}. {TABLES[tag][0]}", style="Report Caption")
            caption.paragraph_format.space_before = Pt(5)
            caption.paragraph_format.keep_with_next = True
        table = self.doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.autofit = False
        for column, width in zip(table.columns, widths):
            column.width = Cm(width)
        repeated = OxmlElement("w:tblHeader")
        table.rows[0]._tr.get_or_add_trPr().append(repeated)
        for index, values in enumerate([headers, *rows]):
            row = table.rows[0] if index == 0 else table.add_row()
            row._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
            for cell, value, width in zip(row.cells, values, widths):
                cell.width = Cm(width)
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                paragraph = cell.paragraphs[0]
                paragraph.style = "Report Table"
                run = paragraph.add_run(str(value))
                if index == 0:
                    run.bold = True
                    shade(cell, "E5EEF7")
                elif index % 2 == 0:
                    shade(cell, "F3F7FB")
        return table

    def figure(self, tag, width=15.8):
        title, _, name = FIGURES[tag]
        directory = SCREENSHOTS if tag.startswith("3") else EXPERIMENTS
        paragraph = self.doc.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_before = Pt(4)
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.paragraph_format.keep_with_next = True
        shape = paragraph.add_run().add_picture(str(directory / name), width=Cm(width))
        shape._inline.docPr.set("descr", title)
        caption = self.doc.add_paragraph(f"Hình {tag}. {title}", style="Report Caption")
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.paragraph_format.space_after = Pt(7)

    def flow(self, nodes):
        for index, text in enumerate(nodes):
            if index:
                arrow = self.centered("↓", bold=True, space=1)
                arrow.paragraph_format.keep_with_next = True
            box = self.centered(text, space=1)
            box.paragraph_format.left_indent = Cm(.8)
            box.paragraph_format.right_indent = Cm(.8)
            box.paragraph_format.keep_with_next = True
            background = OxmlElement("w:shd")
            background.set(qn("w:fill"), "E5EEF7")
            box._p.get_or_add_pPr().append(background)
        caption = self.doc.add_paragraph(
            "Sơ đồ 3.1. Luồng định giá từ yêu cầu đến kết quả", style="Report Caption"
        )
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.paragraph_format.space_after = Pt(7)


def preliminaries(r):
    r.centered("TRƯỜNG ĐẠI HỌC CÔNG NGHIỆP HÀ NỘI", bold=True, size=15)
    r.centered("HỌC PHẦN CÔNG NGHỆ TRI THỨC", bold=True, space=29)
    r.centered("BÁO CÁO BÀI TẬP LỚN", bold=True, size=16, space=11)
    r.centered(TITLE, bold=True, size=22, space=25)
    r.centered("NHÓM 4", bold=True, size=15, space=13)
    r.centered("Giảng viên hướng dẫn  _______________________________", space=15)
    r.table(["Họ và tên thành viên", "Mã sinh viên"], [(" ", " ")] * 4, [10.5, 5.5])
    r.centered("Hà Nội, 2026", bold=True).paragraph_format.space_before = Pt(25)

    r.heading("Mục lục", page=True)
    for item in CONTENTS:
        r.index(*item)

    r.heading("Danh mục hình và bảng", page=True)
    r.heading("Danh mục hình", 2)
    r.index("Sơ đồ 3.1. Luồng định giá từ yêu cầu đến kết quả", 10)
    for tag, (title, page, _) in FIGURES.items():
        r.index(f"Hình {tag}. {title}", page)
    r.heading("Danh mục bảng", 2)
    for tag, (title, page) in TABLES.items():
        r.index(f"Bảng {tag}. {title}", page)

    r.heading("Danh mục từ viết tắt", page=True)
    r.table(["Viết tắt", "Tên và cách sử dụng"], [
        ("CBR", "Case-Based Reasoning · suy luận dựa trên tình huống"),
        ("KB", "Knowledge Base · cơ sở tri thức"),
        ("MAE", "Mean Absolute Error · sai số tuyệt đối trung bình"),
        ("MAPE", "Mean Absolute Percentage Error · sai số phần trăm tuyệt đối trung bình"),
        ("R²", "Hệ số xác định"),
        ("RF", "Random Forest · rừng ngẫu nhiên"),
        ("JSON", "JavaScript Object Notation · định dạng cấu hình"),
        ("CSV", "Comma-Separated Values · dữ liệu dạng bảng"),
        ("CVT", "Continuously Variable Transmission · hộp số vô cấp"),
    ], [2.7, 13.3])
    r.body("Các giá trị tiền trong báo cáo dùng đơn vị triệu đồng. Số km là số đo tích lũy trên đồng hồ, "
           "còn tuổi xe bằng năm tham chiếu trừ năm sản xuất. Bảng và giao diện có thể làm tròn ở độ chính xác khác nhau.")


def theory(r):
    r.heading("Mở đầu", page=True)
    r.heading("Lý do chọn đề tài", 2)
    r.body("Cùng một dòng ô tô cũ có thể được chào giá khác nhau do đời xe, quãng đường đã đi, tình trạng và lịch sử sử dụng. "
           "Người mua cần biết thông tin nào đã tác động tới mức giá để kiểm tra hồ sơ và đặt câu hỏi khi xem xe.")
    r.heading("Mục tiêu và phạm vi", 2)
    r.body("Đề tài xây dựng hệ hỗ trợ định giá tham khảo tại Việt Nam. Ứng dụng nhận thông tin xe và trả về giá, "
           "khoảng tham khảo, mức tin cậy theo quy tắc, cảnh báo và vết tính. Danh mục chỉ gồm các mẫu xe được khai báo trong cơ sở tri thức.")
    r.body("Nhóm sử dụng dữ liệu mô phỏng, giá xe mới và hệ số giả định. Giá mô phỏng là nhãn dùng để thử hệ thống. "
           "Phạm vi đề tài dừng ở mức minh họa học phần và đánh giá trên mô phỏng.")
    r.heading("Phương pháp và kết quả mong muốn", 2)
    r.body("Máy suy diễn tiến áp dụng luật chuyên gia giả định, CBR tìm xe tương tự và hệ lai tổng hợp hai giá. "
           "Thực nghiệm dùng chung tập test để so sánh chỉ luật, chỉ CBR, Random Forest và hệ lai. "
           "Kết quả mong muốn là ứng dụng tiếng Việt chạy được, có bộ dữ liệu tái lập và báo cáo giải được một ca cụ thể đến từng phép tính.")
    r.heading("Cấu trúc báo cáo", 2)
    r.body("Chương 1 trình bày bài toán và cơ sở lý thuyết. Chương 2 mô tả kiến trúc và công thức. Chương 3 theo luồng sử dụng "
           "và giải ca Toyota Vios. Chương 4 trình bày dữ liệu, kết quả, kiểm thử và giới hạn.")

    r.heading("Chương 1. Bài toán và cơ sở lý thuyết", page=True)
    r.heading("1.1 Bài toán định giá tham khảo", 2)
    r.body("Một yêu cầu gồm phiên bản, năm sản xuất, số km, khu vực, tình trạng và bốn cờ lịch sử. Hệ thống cần đưa ra "
           "giá theo đơn vị triệu đồng và cho phép người dùng truy ngược các giả định chi phối kết quả.")
    r.heading("1.2 Khung tri thức và suy diễn tiến", 2)
    r.body("Khung tập hợp các thuộc tính của đối tượng. Trong đề tài, một phiên bản có mã, hãng, dòng, tên, phân khúc và giá "
           "xe mới tham chiếu. Một luật gồm tiền đề và hành động. Máy suy diễn tiến bắt đầu từ các dữ kiện đầu vào, chọn luật "
           "có tiền đề đúng, áp dụng hành động và tiếp tục đối sánh trên tập dữ kiện đã cập nhật [1].")
    r.heading("1.3 Suy luận dựa trên tình huống", 2)
    r.body("CBR tái sử dụng kinh nghiệm từ bài toán gần giống. Chu trình kinh điển gồm truy hồi, tái sử dụng, hiệu chỉnh qua phản hồi "
           "và lưu lại [2]. Hệ thống thực hiện truy hồi theo điểm tương tự và hiệu chỉnh bằng hệ số cố định. Kho được nạp từ train khi khởi động.")
    r.heading("1.4 Đối chứng và độ đo", 2)
    r.body("Random Forest lấy trung bình dự đoán của nhiều cây hồi quy dựa trên lấy mẫu và lựa chọn đặc trưng ngẫu nhiên [3]. "
           "Trong so sánh, MAE là trung bình |y − ŷ| theo triệu đồng. MAPE là 100 lần trung bình |y − ŷ|/y. "
           "R² bằng 1 trừ tỷ lệ tổng bình phương sai số trên tổng bình phương độ lệch của y quanh trung bình [4]. "
           "Giá y trong thực nghiệm luôn dương.")


def design(r, kb):
    r.heading("Chương 2. Thiết kế hệ thống", page=True)
    r.heading("2.1 Kiến trúc và cơ sở tri thức", 2)
    r.body("app.py là điểm vào. src/ui.py tổ chức bốn trang Streamlit, còn src/charts.py dựng biểu đồ Plotly. "
           "src/knowledge.py đọc các tệp JSON, kiểm tra lược đồ và dựng khung. src/inference.py, src/cbr.py và src/pricing.py "
           "thực hiện ba bước định giá. src/experiment.py chạy đánh giá với cùng lõi tính giá.")
    r.body(f"kb/frames.json khai báo {len(kb.frames)} phiên bản dưới cây hãng → dòng → phiên bản. Giá mới là giả định tính theo "
           f"triệu đồng, dùng năm tham chiếu {kb.year}. kb/rules.json có {len(kb.rules)} luật và kb/demos.json có "
           f"{len(kb.demos)} mẫu. kb/settings.json giữ cấu hình CBR và hệ lai.")
    groups = [
        ("TUOI", "Tuổi xe (0–1, 2–3, 4–5, 6–8, 9–11, 12–14, từ 15 năm)"),
        ("KM", "Số km (năm nhóm)"), ("TT", "Tình trạng theo bốn mức"),
        ("BD", "Xác nhận bảo dưỡng hãng"), ("KV", "Khu vực"),
        ("RR", "Chạy dịch vụ, ngập nước, tai nạn nặng và chặn giảm gộp"),
    ]
    r.table(["Nhóm", "Điều kiện và hành động", "Số luật"],
            [(code, detail, sum(rule.id.startswith(code) for rule in kb.rules)) for code, detail in groups],
            [2.3, 11.2, 2.5], "2.1")
    r.body("Sau mỗi lần áp dụng, máy cập nhật giá, số rủi ro và hệ số rủi ro khi phù hợp, rồi so khớp lại các luật chưa dùng. "
           "Ưu tiên lớn hơn được áp dụng trước. Khi bằng ưu tiên, hệ chọn mã theo thứ tự tăng dần. Mỗi luật kích hoạt một lần. "
           "Vết lưu mã, lời giải thích, giá trước, mức thay đổi, giá sau và cảnh báo.")
    r.body("Luật thường chạy trước nhóm rủi ro. Các mức giảm rủi ro nhân lần lượt lên giá hiện tại. Với cả ba cờ, "
           "hệ số tạm là 0,89 × 0,71 × 0,78 = 0,492882. RR-04 nâng hệ số lên 0,58 do ít nhất hai rủi ro "
           "cùng xuất hiện và mức giảm tổng vượt 42%. Ba cảnh báo vẫn được giữ.")

    r.heading("2.2 Truy hồi và hiệu chỉnh tình huống", 2, page=True)
    cbr = kb.settings["cbr"]
    r.body(f"Kho CBR gồm các xe train. Bộ lọc giữ xe cùng hãng và dòng, cùng hai cờ ngập nước và tai nạn nặng, "
           f"chênh đời tối đa {cbr['year_window']} năm. S = Σ(wⱼ × sⱼ). Các xe đạt S ≥ {vi(cbr['threshold'], 2)} "
           f"được sắp theo S giảm dần rồi theo mã xe tăng dần. Giữ tối đa {cbr['limit']} xe và cần ít nhất {cbr['minimum']} xe để tính giá.")
    rows = [
        ("Phiên bản", "trim", "1 nếu cùng phiên bản, 0,40 nếu khác"),
        ("Năm sản xuất", "year", "max(0, 1 − |Δnăm|/5)"),
        ("Số km", "mileage", "max(0, 1 − |Δkm|/120.000)"),
        ("Khu vực", "region", "1 nếu trùng, 0 nếu khác"),
        ("Tình trạng", "condition", "1 − |Δmức|/3, từ Kém (0) đến Tốt (3)"),
        ("Bảo dưỡng hãng", "dealer_service", "1 nếu trùng, 0 nếu khác"),
        ("Chạy dịch vụ", "commercial", "1 nếu trùng, 0 nếu khác"),
    ]
    r.table(["Thuộc tính", "wⱼ", "Điểm khớp sⱼ"],
            [(label, pct(cbr["weights"][key], 0), score) for label, key, score in rows], [4.3, 2.3, 9.4], "2.2")
    r.body("Ký hiệu t là xe cần định giá và i là xe trong kho. Mức tình trạng từ 0 đến 3, cờ đúng bằng 1. "
           "Chênh khu vực lấy từ giả định trong settings.json. Tính Aᵢ từ các chênh lệch sau.")
    r.equation("Aᵢ = 0,045(nămₜ − nămᵢ) + 0,035(kmᵢ − kmₜ)/20.000 + 0,055(mứcₜ − mứcᵢ)")
    r.equation("       + 0,035(bảo dưỡngₜ − bảo dưỡngᵢ) + 0,085(dịch vụᵢ − dịch vụₜ) + (vùngₜ − vùngᵢ)")
    r.body("Nhân (1 + Aᵢ) với tỷ số giá mới của xe t trên xe i, sau đó chặn kết quả trong [0,60; 1,55]. "
           "Giá hiệu chỉnh bằng giá gốc nhân hệ số đã chặn. Giá CBR = Σ(Sᵢ × giá hiệu chỉnhᵢ)/ΣSᵢ. "
           "Các hệ số hiệu chỉnh là giả định độc lập với máy suy diễn.")

    r.heading("2.3 Tổng hợp giá, khoảng và độ tin cậy", 2, page=True)
    r.body("S̄ là trung bình độ tương tự của n xe được giữ. Trọng số CBR tăng theo điểm tương tự và số xe. "
           "Giảm trọng số này khi xe từng ngập nước hoặc tai nạn nặng để dựa thêm vào luật rủi ro có giải thích.")
    r.equation("wCBR = 0,25 + 0,50 × S̄ × n/5. Nhân thêm 0,80 nếu có rủi ro nặng.")
    r.equation("wluật = 1 − wCBR.  P = wluật × Pluật + wCBR × PCBR.")
    r.body("Khi có 0 hoặc 1 xe đủ gần, đặt wCBR = 0, P = Pluật và hiển thị lý do. "
           "Tin cậy thấp với trường hợp này hoặc có ngập nước, tai nạn nặng. Xe dịch vụ có thể đạt mức trung bình.")
    r.body("Khi có kết quả CBR và hồ sơ không có rủi ro, tin cậy cao nếu đủ 5 xe, S̄ ≥ 0,85 và |Pluật − PCBR|/P ≤ 0,12. "
           "Khi không có rủi ro nặng, hệ cho mức trung bình nếu S̄ ≥ 0,76 và chênh lệch tương đối ≤ 0,25. Các ca còn lại có mức thấp.")
    r.body("Nửa độ rộng h cộng ba thành phần. a theo chất lượng chứng cứ, |Pluật − PCBR| phản ánh độ lệch giữa hai giá, "
           "còn D là trung bình có trọng số Sᵢ của độ lệch tuyệt đối giữa các giá hiệu chỉnh và PCBR.")
    r.equation("h = a × P + 0,35 × |Pluật − PCBR| + 0,30 × D")
    r.equation("Khoảng đề xuất = [max(1, P − h); P + h].")
    r.body("Khi có CBR, a = 10%, cộng 3,5 điểm phần trăm nếu ít hơn 5 xe. Nếu thiếu CBR, a = 18% và hai khoản còn lại bằng 0. "
           "Cộng 4 điểm cho ngập nước hoặc tai nạn nặng, và 2 điểm cho chạy dịch vụ. Các ngưỡng là quy tắc giả định. "
           "Mức tin cậy là nhãn đánh giá chất lượng chứng cứ, còn độ phủ được đo thực nghiệm tại Chương 4.")


def implementation(r, demos, kb):
    r.heading("Chương 3. Cài đặt và giao diện", page=True)
    r.heading("3.1 Cài đặt và sơ đồ xử lý", 2)
    r.body("Từ thư mục dự án, tạo môi trường ảo với Python 3.12, cài requirements.txt và chạy app.py bằng Streamlit. "
           "README hướng dẫn Windows, cách chạy lại các script và thao tác trên trình duyệt. "
           "Điều hướng giữa các trang dùng st.navigation [5].")
    r.equation("python -m pip install -r requirements.txt")
    r.equation("python -m streamlit run app.py")
    r.flow([
        "Biểu mẫu → tra khung và kiểm tra đầu vào → dữ kiện xe hợp lệ",
        "Dữ kiện → suy diễn tiến và truy hồi các xe tương tự",
        "Đủ xe tương tự → tổng hợp hai giá. Thiếu xe tương tự → dùng giá luật.",
        "Tính khoảng và tin cậy → lưu kết quả vào phiên → hiển thị và giải thích",
    ])
    r.body("Đoạn mã trong src/inference.py chọn luật có điều kiện đúng trên dữ kiện hiện tại. "
           "Sau khi thực thi, vòng lặp dùng lại các dữ kiện vừa được cập nhật.")
    source = (ROOT / "src" / "inference.py").read_text(encoding="utf-8")
    start = source.index("        rule = next(")
    end = source.index("        if rule is None:", start)
    for line in source[start:end].splitlines():
        p = r.doc.add_paragraph(line[8:], style="Report Table")
        p.paragraph_format.left_indent = Cm(.4)

    normal = demos["normal"]["valuation"]
    flood = demos["flood"]["valuation"]
    r.heading("3.2 Định giá và xem kết quả", 2, page=True)
    r.body("Chọn mẫu xe bình thường để nạp Toyota Vios 1.5G CVT đời 2019, đi 95.000 km. "
           "Các danh sách dòng và phiên bản cập nhật theo lựa chọn phía trước. Người dùng có thể đổi dữ kiện trước khi bấm Định giá.")
    r.figure("3.1")
    r.body(f"Bấm Xem kết quả và giải thích từ tóm tắt. Bốn ô giá và tin cậy nằm trên thanh khoảng giá. Chấm cam "
           f"ở {vi(normal['price'])} triệu đồng là giá đề xuất. Hai đầu mút ở {vi(normal['lower'])} và {vi(normal['upper'])} triệu đồng.")
    r.figure("3.2")

    r.heading("3.3 Giải thích giá", 2, page=True)
    r.body("Tab Giải thích trình bày tỷ trọng của mỗi nguồn, phương trình tổng hợp, nửa độ rộng và lý do xếp mức tin cậy. "
           "Các số thập phân hiển thị được làm tròn, còn phép tính giữ giá trị đầy đủ.")
    r.figure("3.3")
    r.body("Khi thay đổi đầu vào, biểu mẫu yêu cầu định giá lại. Trang kết quả giữ lần tính gần nhất và báo rõ khi dữ kiện nhập đã đổi. "
           "Nếu chưa có lần tính, trang đưa người dùng về biểu mẫu.")

    r.heading("3.4 Vết suy diễn", 2, page=True)
    r.body("Biểu đồ waterfall bắt đầu từ giá xe mới giả định. Mỗi cột trung gian là số tiền thay đổi sau một luật, "
           "và cột cuối là giá theo luật. Bảng bên dưới ghi cả lời giải thích và cảnh báo khi có.")
    r.figure("3.4")
    r.body("Các mã trên biểu đồ nối trực tiếp với bảng vết và tập luật JSON. Trong ca Vios, TUOI-04 tạo mức điều chỉnh tuyệt đối lớn nhất.")

    r.heading("3.5 Xe tương tự", 2, page=True)
    r.body("Tab Xe tương tự trình bày năm xe đứng đầu theo độ tương tự. Bảng cho người xem đối chiếu đời xe, số km, tình trạng, "
           "giá gốc và giá sau hiệu chỉnh. Mục mở rộng bên dưới giải thích tiêu chí và trọng số.")
    r.figure("3.5")
    sparse = demos["sparse"]["valuation"]
    r.body(f"Mẫu Lexus RX 350 Luxury minh họa trường hợp thiếu đối chứng. Kho không có xe cùng dòng, nên giá đề xuất "
           f"{vi(sparse['price'])} triệu đồng lấy toàn bộ từ luật. Giao diện hiển thị lý do và tin cậy thấp.")

    r.heading("3.6 Phân tích dữ liệu", 2, page=True)
    r.body("Trang Phân tích dữ liệu dùng kho train và cập nhật số mẫu, giá trung vị, số dòng xe theo hãng, phân khúc và đời xe. "
           "Ba biểu đồ mô tả phân bố giá, trung vị theo phân khúc và quan hệ giữa tuổi xe với giá.")
    r.figure("3.6")

    r.heading("3.7 Quản trị tri thức", 2, page=True)
    r.body(f"Trang quản trị hiển thị {len(kb.rules)} luật, {len(kb.frames)} khung phiên bản, số tình huống và trạng thái kiểm tra. "
           "Bốn tab cho phép đọc luật, cây khung, kho tình huống và lỗi theo nguồn, vị trí, chi tiết.")
    r.figure("3.7")
    r.body("Kiểm tra nhất quán phát hiện mã trùng, toán tử hoặc hệ số hành động sai miền và tham chiếu tới phiên bản thiếu. "
           "Tập luật và giá tham chiếu có thể chỉnh trong các tệp JSON. Trang định giá báo lỗi nếu cơ sở tri thức có lỗi.")

    r.heading("3.8 Cảnh báo lịch sử", 2, page=True)
    r.body(f"Mẫu xe ngập nước giữ đời 2019 và 95.000 km, đổi tình trạng thành Trung bình, bật cờ ngập nước. "
           f"RR-02 điều chỉnh giá và sinh cảnh báo. Giao diện hiển thị {vi(flood['price'])} triệu đồng với mức tin cậy thấp.")
    r.figure("3.8")
    r.body("Thông báo yêu cầu kiểm tra hệ thống điện, nội thất và dấu gỉ. Khi nhiều rủi ro cùng xuất hiện, "
           "giao diện liệt kê từng cảnh báo, còn vết suy diễn cho thấy khi nào RR-04 được kích hoạt.")


def walkthrough(r, demos, kb):
    r.heading("3.9 Ca Vios từ giá mới đến độ tương tự", 2, page=True)
    demo = demos["normal"]
    result = demo["valuation"]
    vehicle = result["vehicle"]
    rules, cbr = result["inference"], result["cbr"]
    r.body(f"Toyota Vios 1.5G CVT đời {vehicle['year']}, {vi(vehicle['mileage'], 0)} km, Hà Nội, tình trạng Khá. "
           f"Ca này có tuổi {kb.year - vehicle['year']} theo mốc {kb.year}, chưa xác nhận bảo dưỡng hãng và không khai báo ba cờ rủi ro.")
    r.body(f"Khung vios-g có giá mới giả định {vi(rules['reference_price'], 0)} triệu đồng. Máy suy diễn thực hiện các bước sau. "
           "Giá và thay đổi trong bảng được làm tròn đến ba chữ số thập phân.")
    rates = {rule.id: rule.action.value for rule in kb.rules}
    r.table(["Luật", "Trước", "Tỷ lệ", "Thay đổi", "Sau"],
            [(step["rule_id"], vi(step["before"], 3), f"{signed(100 * rates[step['rule_id']], 0)}%",
              signed(step["delta"], 3), vi(step["after"], 3)) for step in rules["steps"]],
            [3.4, 3.15, 2.3, 3.6, 3.55], "3.1")
    r.equation("548 × 0,65 × 0,94 × 0,98 × 0,98 × 1,02 ≈ " + vi(rules["price"], 4) + " triệu đồng.")
    neighbor = cbr["neighbors"][0]
    case, case_vehicle = neighbor["case"], neighbor["case"]["vehicle"]
    cbr_config = kb.settings["cbr"]
    delta_km = abs(vehicle["mileage"] - case_vehicle["mileage"])
    r.body(f"Ví dụ xe gần nhất trong kho là {case['case_id']}, cùng phiên bản, đời {case_vehicle['year']}, "
           f"{vi(case_vehicle['mileage'], 0)} km, Hà Nội, tình trạng Khá, cờ bảo dưỡng và dịch vụ giống xe cần định giá. "
           f"Chỉ điểm khớp số km thấp hơn 1. Chênh lệch là {vi(delta_km, 0)} km.")
    r.equation(f"s(km) = 1 − {vi(delta_km, 0)}/{vi(cbr_config['mileage_scale'], 0)} = {vi(neighbor['components']['mileage'], 4)}.")
    r.equation(f"S = 0,82 + 0,18 × {vi(neighbor['components']['mileage'], 4)} = {vi(neighbor['similarity'], 6)}.")
    r.body(f"Tỷ số giá mới bằng {vi(neighbor['reference_ratio'], 0)}. Phần bù km là "
           f"0,035 × ({vi(case_vehicle['mileage'], 0)} − {vi(vehicle['mileage'], 0)})/20.000 "
           f"= {signed(neighbor['adjustment_terms']['mileage'], 6)}. Các phần bù còn lại bằng 0, nên hệ số "
           f"{vi(neighbor['ratio'], 6)} nằm trong miền chặn.")
    r.equation(f"Giá hiệu chỉnh = {vi(case['price'], 2)} × {vi(neighbor['ratio'], 6)} ≈ {vi(neighbor['adjusted_price'], 3)} triệu đồng.")

    r.heading("3.10 Ca Vios từ giá CBR đến khoảng đề xuất", 2, page=True)
    r.table(["Tình huống", "Sᵢ", "Giá gốc", "Giá hiệu chỉnh", "Sᵢ × giá hiệu chỉnh"],
            [(item["case"]["case_id"], vi(item["similarity"], 6), vi(item["case"]["price"], 2),
              vi(item["adjusted_price"], 3), vi(item["similarity"] * item["adjusted_price"], 3))
             for item in cbr["neighbors"]], [2.8, 2.7, 2.7, 3.5, 4.3], "3.2")
    weight_total = sum(item["similarity"] for item in cbr["neighbors"])
    weighted_total = sum(item["similarity"] * item["adjusted_price"] for item in cbr["neighbors"])
    r.equation(f"PCBR ≈ {vi(weighted_total, 4)}/{vi(weight_total, 6)} = {vi(cbr['price'], 4)} triệu đồng.")
    r.body(f"Năm xe có điểm trung bình S̄ ≈ {vi(cbr['mean_similarity'], 6)}. "
           f"wCBR = 0,25 + 0,50 × S̄ × 5/5 ≈ {pct(result['cbr_weight'], 4)}. "
           f"wluật ≈ {pct(result['rule_weight'], 4)}.")
    r.equation(f"P ≈ {pct(result['rule_weight'], 4)} × {vi(rules['price'], 4)} + "
               f"{pct(result['cbr_weight'], 4)} × {vi(cbr['price'], 4)}")
    r.equation(f"    ≈ {vi(result['price'], 4)} triệu đồng, hiển thị {vi(result['price'])} triệu đồng.")
    r.body(f"Độ rộng dùng phần cơ sở {pct(result['interval_rate'], 0)}. Hai số cộng do lệch nguồn và độ phân tán lần lượt "
           f"là {vi(result['disagreement_addition'], 4)} và {vi(result['spread_addition'], 4)} triệu đồng.")
    r.equation(f"h ≈ {vi(result['interval_rate'] * result['price'], 4)} + "
               f"{vi(result['disagreement_addition'], 4)} + {vi(result['spread_addition'], 4)} "
               f"= {vi(result['upper'] - result['price'], 4)} triệu đồng.")
    r.body(f"Dải hiển thị [{vi(result['lower'])}; {vi(result['upper'])}] triệu đồng. "
           f"Tỷ lệ lệch giá luật và CBR trên P là {pct(abs(rules['price'] - cbr['price']) / result['price'], 2)}, "
           f"đủ sát để nhận mức {result['confidence']} cùng với năm xe, S̄ vượt 0,85 và hồ sơ không bật rủi ro. "
           "Các số liệu trong Hình 3.1–3.5 và demo_results.json cùng xuất phát từ dữ liệu và phép tính trên.")
    dealer = demos["dealer"]["valuation"]
    r.body(f"Đổi riêng bảo dưỡng sang Có, giá luật tăng từ {vi(rules['price'])} lên "
           f"{vi(dealer['inference']['price'])} triệu đồng. Giá lai còn {vi(dealer['price'])} triệu đồng "
           "do tập xe truy hồi và giá CBR thay đổi. Độ nhạy này là một giới hạn của kho mô phỏng.")


def experiments(r, preparation, results, browser, pytest_summary):
    r.heading("Chương 4. Dữ liệu và thực nghiệm", page=True)
    r.heading("4.1 Dữ liệu, làm sạch và phân chia", 2)
    r.body(f"Script sinh dữ liệu lấy mẫu theo độ phổ biến giả định, với seed {preparation['seed']} và năm "
           f"{preparation['reference_year']}. Số km phụ thuộc tuổi và việc chạy dịch vụ. Tình trạng phụ thuộc tuổi, "
           "bảo dưỡng và cờ rủi ro. Giá sinh từ giá mới, khấu hao liên tục, vùng, mức sử dụng, lịch sử và nhiễu log-normal.")
    r.body("Mỗi dòng có case_id, frame_id, year, mileage (km), region, condition, bốn cờ dealer_service, commercial, "
           "flood và major_accident, cùng price (triệu đồng). Data raw có bản ghi trùng và lỗi được thêm có chủ đích.")
    labels = ["Chuẩn hóa kiểu và khoảng trắng", "Lọc giá sai miền", "Lọc năm sai miền", "Lọc số km sai miền",
              "Lọc mã và trường phân loại sai", "Bỏ mã trùng", "Bỏ đầu vào trùng"]
    r.table(["Bước", "Trước", "Sau", "Loại"], [(label, vi(item["before"], 0), vi(item["after"], 0), item["removed"])
              for label, item in zip(labels, preparation["steps"])], [9, 2.4, 2.4, 2.2], "4.1")
    r.body(f"Chia 80/20 sau khi làm sạch, train có {vi(preparation['train'], 0)} xe và test {vi(preparation['test'], 0)} xe. "
           "Kho CBR, biểu đồ phân tích và huấn luyện RF dùng train. Năm tham chiếu, luật, tham số truy hồi và RF được "
           "ấn định trước khi đánh giá. Trình chạy kiểm tra giao nhau ở cả mã và bộ thuộc tính đầu vào.")

    r.heading("4.2 Kết quả bốn phương pháp", 2, page=True)
    common = [item for item in results["metrics"] if item["scope"] == "common_cbr"]
    full = {item["method"]: item for item in results["metrics"] if item["scope"] == "full_test"}
    r.body(f"Bốn phương pháp được chạy trên {results['test_n']} xe. CBR không đủ xe ở {results['cbr_missing']} ca. "
           f"Ba độ đo trong Bảng 4.2 dùng cùng {results['common_n']} xe có giá CBR. Ca thiếu để trống ở cột CBR "
           "trong predictions.csv. Hệ lai dùng giá luật ở các ca đó.")
    r.table(["Phương pháp", "MAE (tr. đ)", "MAPE (%)", "R²", "Tổng (ms)", "ms/xe"],
            [(item["label"], vi(item["mae_million"], 2), vi(item["mape_percent"], 2), vi(item["r2"], 4),
              vi(item["total_ms"], 2), vi(item["ms_per_vehicle"], 3)) for item in common],
            [3.9, 2.35, 2.6, 1.65, 2.95, 2.55], "4.2")
    r.figure("4.1")
    winner = min(common, key=lambda item: item["mae_million"])
    r.body(f"{winner['label']} có MAE thấp nhất trên phần test chung. Trên toàn bộ {results['test_n']} ca, MAE của luật, "
           f"Random Forest và hệ lai lần lượt là {vi(full['rules']['mae_million'], 2)}, "
           f"{vi(full['random_forest']['mae_million'], 2)} và {vi(full['hybrid']['mae_million'], 2)} triệu đồng.")
    rf = results["rf_params"]
    r.body(f"RF dùng {rf['n_estimators']} cây, lá ít nhất {rf['min_samples_leaf']} mẫu, mã hóa one-hot và một luồng. "
           f"Thời gian fit là {vi(results['timing']['rf_fit_ms'], 1)} ms. Bảng đo dự đoán toàn bộ {results['test_n']} ca, "
           "ngoài thời gian nạp tệp và fit. RF dự đoán theo lô. Thời gian thay đổi theo máy và lần chạy.")

    r.heading("4.3 Khoảng giá hệ lai", 2, page=True)
    interval = results["interval"]
    r.body(f"Giá mô phỏng nằm trong khoảng của hệ lai ở {interval['covered_n']}/{interval['n']} ca, "
           f"tương đương {vi(interval['coverage_percent'], 2)}%. Độ rộng trung bình "
           f"là {vi(interval['mean_width_million'], 2)} triệu đồng. Kết quả gồm cả các lượt dùng giá luật thay thế CBR.")
    r.figure("4.2")
    r.body("Hình 4.2 lấy 32 vị trí cách đều trên thứ tự giá mô phỏng để thấy độ rộng đổi theo giá trị xe. "
           "Chấm là giá mô phỏng, đường cam là giá đề xuất và dải tô xanh là khoảng. Tỷ lệ phủ được tính trên toàn bộ tập test.")
    r.body("Khoảng giá được mở rộng khi thiếu xe tương tự, có rủi ro, chênh giữa hai phương pháp hoặc xe truy hồi có giá phân tán. "
           "Giữa độ rộng và độ phủ có đánh đổi. Với dữ liệu giao dịch thật, cần đánh giá lại cả hai độ đo theo nhóm giá và lịch sử.")

    r.heading("4.4 Kiểm thử và giới hạn", 2, page=True)
    if pytest_summary:
        r.body(f"Pytest ghi nhận {pytest_summary['passed']}/{pytest_summary['total']} ca đạt. "
               "Các test kiểm tra điều kiện biên, công thức, dữ liệu lỗi, tách train/test và số liệu xuất ra.")
    else:
        r.body("Bộ kiểm thử pytest trong tests/ kiểm tra điều kiện biên, công thức, dữ liệu lỗi, tách train/test và số liệu xuất ra.")
    r.body(f"Playwright kiểm tra {browser['passed']} ca trên {browser['browser']} ở chiều rộng {browser['viewport'][0]} px. "
           "Bảng 4.3 trích kết quả quan sát, còn toàn bộ lần kiểm tra được lưu cùng tám ảnh chụp.")
    picked = (1, 2, 3, 6, 7, 8, 10)
    r.table(["Ca kiểm thử", "Kết quả quan sát"], [(browser["checks"][index]["case"], browser["checks"][index]["observed"])
              for index in picked], [6.1, 9.9], "4.3")
    r.body("Giá mới và nhãn đều là mô phỏng. Cùng một giá tham chiếu được dùng qua các đời xe của phiên bản. "
           "Các tập được chia ngẫu nhiên trong cùng bộ sinh, vì vậy sai số có thể thấp hơn khi đổi nguồn, thời điểm hoặc danh mục. "
           "Xe hiếm, xe có nhiều rủi ro và xe thiếu hồ sơ có ít đối chứng. Hệ số rủi ro, ngưỡng truy hồi và mức tin cậy cần được kiểm tra lại với dữ liệu thực.")


def conclusion(r, results):
    r.heading("Kết luận và hướng phát triển", page=True)
    r.body("Hệ thống thực hiện định giá tham khảo và giải thích theo hai hướng. Vết suy diễn định lượng thay đổi từ giá mới, "
           "còn CBR đưa ra các xe đối chứng cùng giá hiệu chỉnh. Luồng Vios nối được giá nhập, mã luật, tình huống, phép tổng hợp và khoảng hiển thị.")
    r.body(f"Trong thử nghiệm mô phỏng, CBR có sai số thấp nhất trên {results['common_n']} ca có đủ đối chứng. Hệ lai "
           f"phủ đủ {results['test_n']} lượt dự đoán nhờ giá luật ở {results['cbr_missing']} ca CBR thiếu kết quả.")
    r.body("Bước phát triển tiếp theo là thu thập giao dịch có kiểm tra tình trạng và thời điểm, đối chiếu từng hệ số với người thẩm định, "
           "chia kiểm thử theo mốc thời gian và theo dòng chưa xuất hiện trong train. Dữ liệu mới sẽ hỗ trợ kiểm tra độ phủ và điều chỉnh khoảng theo nhóm.")
    r.heading("Tài liệu tham khảo", 1)
    bibliography = [
        ("[1] CLIPS, tài liệu chính thức về hệ luật, facts, agenda và salience.",
         "https://www.clipsrules.net/Documentation.html"),
        ("[2] Aamodt, A. & Plaza, E. (1994). Case-Based Reasoning: Foundational Issues, Methodological Variations, "
         "and System Approaches. AI Communications, 7(1), 39–59.",
         "https://journals.sagepub.com/doi/abs/10.3233/AIC-1994-7104"),
        ("[3] Breiman, L. (2001). Random Forests. Machine Learning, 45, 5–32.",
         "https://link.springer.com/article/10.1023/A:1010933404324"),
        ("[4] scikit-learn. Model evaluation, regression metrics.",
         "https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics"),
        ("[5] Streamlit. API reference, st.navigation.", "https://docs.streamlit.io/develop/api-reference/navigation/st.navigation"),
    ]
    for reference, url in bibliography:
        p = r.doc.add_paragraph(f"{reference}\n{url}")
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT


def read_pytest(path):
    if path is None:
        return None
    cases = list(ElementTree.parse(path).iter("testcase"))
    passed = sum(not any(case.find(node) is not None for node in ("failure", "error", "skipped")) for case in cases)
    return {"total": len(cases), "passed": passed}


def render(path, pytest_summary):
    kb = load_knowledge(KB_DIR)
    kb.require_valid()
    demos = read_json(EXPERIMENTS / "demo_results.json")
    preparation = read_json(DATA_DIR / "preparation.json")
    metrics = read_json(EXPERIMENTS / "metrics.json")
    browser = read_json(SCREENSHOTS / "browser_checks.json")
    report = Report()
    preliminaries(report)
    theory(report)
    design(report, kb)
    implementation(report, demos, kb)
    walkthrough(report, demos, kb)
    experiments(report, preparation, metrics, browser, pytest_summary)
    conclusion(report, metrics)
    report.doc.save(path)


def export_pdf(docx, soffice):
    with TemporaryDirectory(prefix="dinh-gia-xe-") as tmp:
        temp = Path(tmp)
        profile = (temp / "lo-profile").as_uri()
        subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless", "--convert-to",
                        "pdf:writer_pdf_Export", "--outdir", str(temp), str(docx)], check=True)
        converted = temp / docx.with_suffix(".pdf").name
        if not converted.is_file():
            raise RuntimeError("LibreOffice không tạo PDF.")
        shutil.move(converted, docx.with_suffix(".pdf"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", action="store_true", help="Xuất thêm PDF")
    parser.add_argument("--soffice", default=shutil.which("soffice"), help="Đường dẫn đến LibreOffice soffice")
    parser.add_argument("--junit", type=Path, help="XML kết quả pytest, tạo bằng --junitxml")
    args = parser.parse_args()

    REPORT.mkdir(parents=True, exist_ok=True)
    path = REPORT / f"{NAME}.docx"
    render(path, read_pytest(args.junit))
    print(f"Đã tạo {path.relative_to(ROOT)}.", flush=True)
    if args.pdf:
        if not args.soffice:
            parser.error("Cài LibreOffice hoặc truyền --soffice để xuất PDF.")
        export_pdf(path, args.soffice)
        print(f"Đã tạo {path.with_suffix('.pdf').relative_to(ROOT)}.", flush=True)


if __name__ == "__main__":
    main()
