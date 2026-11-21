"""Các trang Streamlit của hệ hỗ trợ định giá."""

from dataclasses import asdict
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from . import charts
from .cbr import CaseBase
from .datasets import case_dataframe, load_cases
from .knowledge import DATA_DIR, KB_DIR, load_knowledge
from .models import Vehicle
from .presentation import pct, signed, table_html, vi
from .pricing import valuate

FLAG_LABELS = {
    "dealer_service": "Bảo dưỡng hãng", "commercial": "Từng chạy dịch vụ",
    "flood": "Từng ngập nước", "major_accident": "Tai nạn nặng",
}
FIELD_LABELS = {
    "age": "Tuổi", "year": "Đời xe", "mileage": "Số km", "condition": "Tình trạng", "region": "Khu vực",
    "risk_count": "Số rủi ro", "risk_multiplier": "Hệ số rủi ro", "trim": "Phiên bản",
    "frame_id": "Mã khung", "segment": "Phân khúc", "price": "Giá", **FLAG_LABELS,
}
ACTION_LABELS = {"adjust_percent": "Điều chỉnh", "apply_risk": "Khấu trừ rủi ro", "floor_risk_multiplier": "Sàn hệ số"}
WIDGET_FIELDS = ("frame_id", "year", "mileage", "region", "condition", *FLAG_LABELS)


@st.cache_resource(show_spinner=False)
def resources(revision):
    kb = load_knowledge()
    cases, issues = load_cases(DATA_DIR / "train.csv", kb) if kb.frames else ((), ())
    return kb, CaseBase(kb, cases), issues


def file_revision() -> tuple:
    files = [*sorted(KB_DIR.glob("*.json")), DATA_DIR / "train.csv"]
    return tuple((path.name, path.stat().st_mtime_ns if path.exists() else None) for path in files)


def hero(title, subtitle, *, compact=False):
    style = 'hero result-title' if compact else 'hero'
    st.html(
        f'<section class="{style}"><div><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>'
        '<span class="pill">Dữ liệu mô phỏng</span></section>'
    )


def section_title(title, note=None):
    description = f'<p class="section-note">{escape(note)}</p>' if note else ""
    st.html(f'<div class="section-title">{escape(title)}</div>{description}')


def metric(label, value, *, unit="", style="", sub=""):
    units = f' <span class="unit">{escape(unit)}</span>' if unit else ""
    description = f'<div class="sub">{escape(sub)}</div>' if sub else ""
    st.html(
        f'<section class="metric-card {style}"><div class="caption">{escape(label)}</div>'
        f'<div class="value">{escape(value)}{units}</div>{description}</section>'
    )


def price_text(value):
    return vi(value) if value is not None else "—"


def chart(fig, *, key):
    st.plotly_chart(fig, width="stretch", config=charts.CHART_OPTIONS, key=key)


def vehicle_description(vehicle, frame):
    return f"{vehicle.year} · {vi(vehicle.mileage, 0)} km · {vehicle.region} · {vehicle.condition} · {frame.segment}"


def _restore_form(vehicle, kb, field_key):
    state = st.session_state
    for field, value in asdict(vehicle).items():
        state[field_key(field)] = value
    frame = kb.frames[vehicle.frame_id]
    state[field_key("brand")], state[field_key("model")] = frame.brand, frame.model


def form_page(kb, library, result_page):
    hero("Định giá ô tô cũ", "Tính giá tham khảo từ cơ sở tri thức và các tình huống xe tương tự tại Việt Nam.")
    if kb.issues:
        st.error("Cơ sở tri thức có lỗi. Xem chi tiết tại Quản trị tri thức.")
        return
    state = st.session_state
    demos = {demo.id: demo for demo in kb.demos}
    if "draft" not in state:
        state.draft = kb.demos[0].vehicle
        state.selected_demo = kb.demos[0].id
        state.form_generation = 0
    generation = state.form_generation

    def field_key(field):
        return f"form_{generation}_{field}"

    if field_key("frame_id") not in state:
        draft = state.draft if state.draft.frame_id in kb.frames else kb.demos[0].vehicle
        _restore_form(draft, kb, field_key)
    if "form_demo" not in state:
        state.form_demo = state.selected_demo

    by_brand = {}
    for frame in kb.frames.values():
        by_brand.setdefault(frame.brand, {}).setdefault(frame.model, []).append(frame.id)

    def set_model_frame():
        state[field_key("frame_id")] = by_brand[state[field_key("brand")]][state[field_key("model")]][0]

    def set_brand_model():
        state[field_key("model")] = next(iter(by_brand[state[field_key("brand")]]))
        set_model_frame()

    def load_demo():
        chosen = demos[state.form_demo]
        state.draft = chosen.vehicle
        state.selected_demo = chosen.id
        # Mẫu mới dùng bộ khóa mới để trình duyệt không gửi lại giá trị của mẫu trước.
        state.form_generation += 1

    with st.container(border=True, key="panel_demo"):
        info, selector, reload = st.columns([1.35, .85, .34], vertical_alignment="bottom")
        with info:
            section_title("Mẫu định giá", "Chọn mẫu để điền nhanh. Bạn có thể sửa các thông tin bên dưới.")
        with selector:
            st.selectbox("Chọn mẫu", list(demos), format_func=lambda code: demos[code].label,
                         key="form_demo", on_change=load_demo)
        with reload:
            st.button("Nạp mẫu", on_click=load_demo, width="stretch")

    first, second, third = st.columns([1.04, 1, 1.13])
    with first, st.container(border=True, height="stretch", key="panel_identity"):
        section_title("Nhận diện xe")
        st.selectbox("Hãng", list(by_brand), key=field_key("brand"), on_change=set_brand_model)
        models = by_brand[state[field_key("brand")]]
        st.selectbox("Dòng", list(models), key=field_key("model"), on_change=set_model_frame)
        st.selectbox("Phiên bản", models[state[field_key("model")]], key=field_key("frame_id"),
                     format_func=lambda code: kb.frames[code].name)
        frame = kb.frames[state[field_key("frame_id")]]
        st.caption(f"Giá mới giả định · {vi(frame.new_price, 0)} triệu ₫")
    with second, st.container(border=True, height="stretch", key="panel_usage"):
        section_title("Mức sử dụng")
        st.number_input("Năm sản xuất", value=None, step=1, format="%d", key=field_key("year"))
        st.number_input("Số km", value=None, step=1000, format="%d", key=field_key("mileage"))
        st.selectbox("Khu vực", list(kb.settings["region_offsets"]), key=field_key("region"))
        st.caption(f"Năm tham chiếu · {kb.year}")
    with third, st.container(border=True, height="stretch", key="panel_condition"):
        section_title("Tình trạng và lịch sử")
        st.selectbox("Tình trạng", list(reversed(kb.settings["conditions"])), key=field_key("condition"))
        for field, label in FLAG_LABELS.items():
            st.checkbox(label, key=field_key(field))

    state.draft = Vehicle(**{field: state[field_key(field)] for field in WIDGET_FIELDS})
    action, tip = st.columns([1, 3.7], vertical_alignment="center")
    with action:
        compute = st.button("Định giá", type="primary", width="stretch", icon=":material/calculate:")
    with tip:
        st.caption("Giá mới và hệ số là giả định dùng cho bài thực nghiệm.")
    if compute:
        errors = kb.vehicle_errors(state.draft)
        if errors:
            st.error(" ".join(errors))
        else:
            state.valuation = valuate(state.draft, kb, library)
    result = state.get("valuation")
    if result is None:
        return
    if state.draft != result.vehicle:
        st.warning("Thông tin xe đã thay đổi. Cần định giá lại để cập nhật kết quả.", icon=":material/refresh:")
        return

    with st.container(border=True, key="panel_brief"):
        brief, estimate, more = st.columns([1.4, .85, 1.1], vertical_alignment="center")
        with brief:
            section_title("Kết quả tóm tắt", kb.frames[result.vehicle.frame_id].title)
        with estimate:
            metric("Giá đề xuất", vi(result.price), unit="triệu ₫", style="lead")
        with more:
            if st.button("Xem kết quả và giải thích", width="stretch", icon=":material/arrow_forward:"):
                st.switch_page(result_page)


def explain(result, kb):
    config = kb.settings["hybrid"]
    weights = st.columns(2)
    with weights[0]:
        metric("Trọng số luật", pct(result.rule_weight), sub=f"{vi(result.inference.price)} triệu ₫")
    with weights[1]:
        metric("Trọng số CBR", pct(result.cbr_weight),
               sub=f"{vi(result.cbr.price)} triệu ₫" if result.cbr.price is not None else "Thiếu tình huống đạt ngưỡng")
    formula = vi(result.inference.price)
    if result.cbr.price is not None:
        formula = (f"{pct(result.rule_weight, 2)} × {vi(result.inference.price, 2)} + "
                   f"{pct(result.cbr_weight, 2)} × {vi(result.cbr.price, 2)}")
    rule = "Giá đề xuất lấy toàn bộ từ máy suy diễn." if result.cbr.price is None else "Phép tính dùng giá và trọng số chưa làm tròn."
    st.html(f'<div class="formula"><strong>{formula} ≈ {vi(result.price)} triệu ₫</strong><p>{rule}</p></div>')
    if result.cbr.reason:
        st.info(result.cbr.reason, icon=":material/info:")
    else:
        n = len(result.cbr.neighbors)
        limit = kb.settings["cbr"]["limit"]
        risk = f" Nhân thêm {vi(config['severe_weight_factor'], 2)} do có rủi ro nặng." if result.vehicle.severe else ""
        st.markdown(
            f"**Trọng số CBR** = {pct(config['base_cbr_weight'], 0)} + {pct(config['quality_cbr_weight'], 0)}"
            f" × {pct(result.cbr.mean_similarity, 2)} × {n}/{limit}.{risk} "
            "Trọng số của luật bằng phần còn lại."
        )
    half = result.interval_rate * result.price + result.disagreement_addition + result.spread_addition
    st.markdown(f"**Nửa độ rộng khoảng** = {pct(result.interval_rate)} × giá đề xuất"
                f" + {vi(result.disagreement_addition, 2)} + {vi(result.spread_addition, 2)}"
                f" ≈ **{vi(half, 2)} triệu ₫**. Hai số cộng phản ánh chênh lệch giữa hai phương pháp "
                "và độ phân tán của giá xe đã hiệu chỉnh.")
    st.caption(f"Tin cậy {result.confidence.lower()} · {result.confidence_reason}")


def trace(result):
    section_title("Từ giá mới giả định đến giá theo luật")
    chart(charts.waterfall(result.inference), key="waterfall")
    rows = [(step.rule_id, vi(step.before), signed(step.delta), vi(step.after),
             step.explanation + (f" {step.warning}" if step.warning else "")) for step in result.inference.steps]
    st.html(table_html(["Mã luật", "Trước (tr. ₫)", "Thay đổi", "Sau (tr. ₫)", "Giải thích"], rows))
    st.caption("Các tỷ lệ tính trên giá ngay trước bước tương ứng. Nhóm rủi ro áp dụng sau các luật thông thường.")


def similar(result, kb):
    config = kb.settings["cbr"]
    section_title("Các tình huống gần nhất",
                  f"Tối đa {config['limit']} xe cùng dòng, cùng cờ ngập nước và tai nạn nặng. "
                  f"Ngưỡng {pct(config['threshold'], 0)}.")
    if not result.cbr.neighbors:
        st.info(result.cbr.reason, icon=":material/info:")
        return
    rows = []
    for item in result.cbr.neighbors:
        case, vehicle = item.case, item.case.vehicle
        rows.append((case.case_id, kb.frames[vehicle.frame_id].name, vehicle.year, vi(vehicle.mileage, 0), vehicle.condition,
                     pct(item.similarity, 2), vi(case.price, 2), vi(item.adjusted_price, 2)))
    st.html(table_html(["Tình huống", "Phiên bản", "Đời xe", "Số km", "Tình trạng", "Tương tự",
                        "Giá gốc (tr. ₫)", "Hiệu chỉnh (tr. ₫)"], rows))
    st.caption("Giá CBR là trung bình giá đã hiệu chỉnh, có trọng số bằng độ tương tự của từng xe.")
    if result.cbr.reason:
        st.info(result.cbr.reason, icon=":material/info:")
    with st.expander("Cách tính độ tương tự và hiệu chỉnh"):
        st.write("Tổng có trọng số của mức khớp từng thuộc tính. Chênh lệch đời xe tối đa "
                 f"{config['year_window']} năm. Điểm đời xe và số km giảm tuyến tính theo mức chênh lệch.")
        weights = [(FIELD_LABELS[name], pct(weight, 0)) for name, weight in config["weights"].items()]
        st.html(table_html(["Thuộc tính", "Trọng số"], weights))
        st.write("Giá hiệu chỉnh bằng giá tình huống nhân tỷ số giá mới và hệ số chênh lệch sử dụng, "
                 "tình trạng, bảo dưỡng, chạy dịch vụ và khu vực. Tỷ số cuối được chặn trong "
                 f"[{vi(config['min_ratio'], 2)}; {vi(config['max_ratio'], 2)}].")


def result_screen(kb, form):
    result = st.session_state.get("valuation")
    if result is None:
        hero("Kết quả và giải thích", "Định giá một xe để xem khoảng giá, vết suy diễn và các xe tương tự.")
        st.page_link(form, label="Quay về form định giá", icon=":material/arrow_back:")
        return
    vehicle = result.vehicle
    if vehicle.frame_id not in kb.frames:
        st.warning("Phiên bản đã thay đổi trong cơ sở tri thức. Hãy định giá lại.")
        st.page_link(form, label="Quay về form định giá", icon=":material/arrow_back:")
        return
    frame = kb.frames[vehicle.frame_id]
    hero(frame.title, vehicle_description(vehicle, frame), compact=True)
    if st.session_state.draft != vehicle:
        st.warning("Đang hiển thị lần tính trước. Quay về form để định giá lại đầu vào đã thay đổi.")
    columns = st.columns(4)
    with columns[0]:
        metric("Giá đề xuất", vi(result.price), unit="triệu ₫", style="lead")
    with columns[1]:
        metric("Giá theo luật", vi(result.inference.price), unit="triệu ₫")
    with columns[2]:
        metric("Giá CBR", price_text(result.cbr.price), unit="triệu ₫" if result.cbr.price is not None else "",
               sub=f"{len(result.cbr.neighbors)} xe đạt ngưỡng")
    with columns[3]:
        metric("Mức tin cậy", result.confidence, style="confidence", sub="Theo quy tắc")
    with st.container(border=True, key="panel_range"):
        st.html('<div class="range-head"><div class="section-title">Khoảng giá tham khảo</div><small>Triệu đồng</small></div>')
        chart(charts.price_range(result), key="price_range")
    if result.inference.warnings:
        items = "".join(f"<p>{escape(warning)}</p>" for warning in result.inference.warnings)
        st.html(f'<div class="risk-note" role="alert"><p><strong>Cảnh báo lịch sử xe</strong></p>{items}</div>')
    explanations, steps, neighbors = st.tabs(["Giải thích", "Vết suy diễn", "Xe tương tự"])
    with explanations:
        explain(result, kb)
    with steps:
        trace(result)
    with neighbors:
        similar(result, kb)


def analytics_page(kb, library):
    hero("Phân tích dữ liệu", "Khám phá giá và mức sử dụng của các xe trong kho tình huống train.")
    data = case_dataframe(library.cases, kb)
    if data.empty:
        st.info("Chưa có tình huống hợp lệ để phân tích.")
        return
    with st.container(border=True, key="panel_filters"):
        a, b, c = st.columns([1, 1.1, 1.5])
        with a:
            brands = st.multiselect("Hãng", sorted(data["Hãng"].unique()), placeholder="Tất cả hãng")
        with b:
            segments = st.multiselect("Phân khúc", sorted(data["Phân khúc"].unique()), placeholder="Tất cả phân khúc")
        with c:
            min_year, max_year = int(data["Đời xe"].min()), int(data["Đời xe"].max())
            if min_year == max_year:
                st.caption(f"Đời xe · {min_year}")
                years = min_year, max_year
            else:
                years = st.slider("Đời xe", min_year, max_year, (min_year, max_year), format="%d")
    filtered = data[data["Đời xe"].between(*years)]
    if brands:
        filtered = filtered[filtered["Hãng"].isin(brands)]
    if segments:
        filtered = filtered[filtered["Phân khúc"].isin(segments)]
    count, price, model = st.columns(3)
    with count:
        metric("Số mẫu", vi(len(filtered), 0))
    with price:
        metric("Giá trung vị", vi(filtered["Giá (triệu ₫)"].median()) if len(filtered) else "—", unit="triệu ₫")
    with model:
        metric("Số dòng xe", vi(len(filtered[["Hãng", "Dòng"]].drop_duplicates()), 0))
    if filtered.empty:
        st.info("Bộ lọc hiện tại không có xe phù hợp.")
        return
    left, right = st.columns(2)
    with left, st.container(border=True, key="panel_distribution"):
        section_title("Phân bố giá")
        chart(charts.distribution(filtered), key="distribution")
    with right, st.container(border=True, key="panel_segments"):
        section_title("Giá trung vị theo phân khúc")
        chart(charts.segment_medians(filtered), key="segments")
    with st.container(border=True, key="panel_ages"):
        section_title("Tuổi xe và giá")
        chart(charts.age_prices(filtered), key="ages")


def _cell_value(value):
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if isinstance(value, float):
        return vi(value, 2)
    return str(value)


def admin_page(kb, cases, case_issues):
    hero("Quản trị tri thức", "Kiểm tra luật, giá tham chiếu và dữ liệu dùng cho truy hồi tình huống.")
    issues = (*kb.issues, *case_issues)
    counts = st.columns(4)
    for col, label, count in zip(counts, ("Tập luật", "Khung xe", "Kho tình huống"),
                                 (len(kb.rules), len(kb.frames), len(cases.cases))):
        with col:
            metric(label, vi(count, 0))
    with counts[3]:
        metric("Kiểm tra nhất quán", f"{len(issues)} lỗi" if issues else "Hợp lệ",
               style="lead" if issues else "confidence")
    rules_tab, frames_tab, cases_tab, check_tab = st.tabs(
        ["Tập luật", "Khung xe", "Kho tình huống", "Kiểm tra nhất quán"]
    )
    with rules_tab:
        section_title("Tập luật định giá", "Các luật được xét theo độ ưu tiên giảm dần, sau đó theo mã.")
        rows = [
            {"Mã": rule.id, "Ưu tiên": rule.priority,
             "Điều kiện": " và ".join(f"{FIELD_LABELS[c.field]} {c.op} {_cell_value(c.value)}" for c in rule.conditions),
             "Hành động": (f"{ACTION_LABELS[rule.action.type]} · " +
                           (pct(rule.action.value, 0) if rule.action.type == "floor_risk_multiplier"
                            else f"{signed(rule.action.value * 100, 0)}%")),
             "Giải thích": rule.explanation}
            for rule in kb.rules
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, height=478,
                     column_config={"Mã": st.column_config.TextColumn(width="small"),
                                    "Ưu tiên": st.column_config.NumberColumn(width="small"),
                                    "Điều kiện": st.column_config.TextColumn(width="medium"),
                                    "Giải thích": st.column_config.TextColumn(width="large")})
    with frames_tab:
        section_title("Hãng → dòng → phiên bản", "Giá xe mới tham chiếu là giả định, tính theo triệu đồng.")
        rows = [{"Mã": f.id, "Hãng": f.brand, "Dòng": f.model, "Phiên bản": f.name, "Phân khúc": f.segment,
                 "Giá mới (triệu ₫)": f.new_price} for f in kb.frames.values()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, height=478)
    with cases_tab:
        section_title("Kho tình huống train", "Kho truy hồi sử dụng dữ liệu mô phỏng đã làm sạch.")
        st.dataframe(case_dataframe(cases.cases, kb), hide_index=True, height=478)
    with check_tab:
        section_title("Kiểm tra nhất quán", "Mã trùng, điều kiện, hành động, thứ tự ưu tiên và tham chiếu khung.")
        if issues:
            st.error(f"Phát hiện {len(issues)} lỗi trong cơ sở tri thức hoặc kho tình huống.")
            st.html(table_html(["Nguồn", "Vị trí", "Chi tiết"], [(i.source, i.location, i.message) for i in issues]))
        else:
            st.success("Mã duy nhất, điều kiện và hành động hợp lệ. Tất cả tham chiếu đều có khung tương ứng.")


def main():
    st.set_page_config(page_title="Định giá xe cũ", page_icon=":material/directions_car:",
                       layout="wide", initial_sidebar_state="expanded")
    st.html(Path(__file__).with_name("style.css"))
    kb, cases, case_issues = resources(file_revision())

    def input_page():
        form_page(kb, cases, result)

    def result_page():
        result_screen(kb, form)

    def data_page():
        analytics_page(kb, cases)

    def knowledge_page():
        admin_page(kb, cases, case_issues)

    form = st.Page(input_page, title="Định giá", icon=":material/directions_car:", default=True)
    result = st.Page(result_page, title="Kết quả và giải thích", icon=":material/receipt_long:", url_path="ket-qua")
    data = st.Page(data_page, title="Phân tích dữ liệu", icon=":material/monitoring:", url_path="phan-tich")
    admin = st.Page(knowledge_page, title="Quản trị tri thức", icon=":material/account_tree:", url_path="tri-thuc")
    pages = [form, result, data, admin]
    page = st.navigation(pages, position="hidden")
    with st.sidebar:
        st.html('<div class="side-brand"><strong>Định giá xe cũ</strong><span>Hệ hỗ trợ quyết định</span></div>')
        for item in pages:
            st.page_link(item)
        st.html('<div class="side-info">Công nghệ tri thức · Nhóm 4<br>Đại học Công nghiệp Hà Nội</div>')
    page.run()
