"""Chạy ca kiểm thử UI và chụp 8 ảnh trực tiếp từ ứng dụng Streamlit."""

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

from src.knowledge import DATA_DIR, OUTPUTS
from src.presentation import pct, vi

OUTPUT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1440, 1160
DEMO = OUTPUTS / "experiments" / "demo_results.json"


def capture(url, chromium):
    demos = json.loads(DEMO.read_text(encoding="utf-8"))
    preparation = json.loads((DATA_DIR / "preparation.json").read_text(encoding="utf-8"))
    images, checks, page_errors = [], [], []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=chromium)
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
        page.set_default_timeout(9000)
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        main = page.get_by_test_id("stMain")
        sidebar = page.get_by_test_id("stSidebar")

        def button(name):
            return main.get_by_role("button", name=re.compile(f"{re.escape(name)}$"))

        def go(name):
            sidebar.get_by_role("link", name=re.compile(f"{re.escape(name)}$")).click()

        def select(label, option):
            main.get_by_role("combobox", name=re.compile(f"{re.escape(label)}$")).click()
            page.get_by_role("option", name=option, exact=True).click()

        def selected(label, option):
            pattern = re.compile(rf"Selected {re.escape(option)}\.\s*{re.escape(label)}$")
            expect(main.get_by_role("combobox", name=pattern)).to_be_visible()

        def choose_demo(code):
            demo = demos[code]
            select("Chọn mẫu", demo["label"])
            frame, vehicle = demo["frame"], demo["valuation"]["vehicle"]
            selected("Hãng", frame["brand"])
            selected("Dòng", frame["model"])
            selected("Phiên bản", frame["name"])
            selected("Tình trạng", vehicle["condition"])
            for label, field in (("Năm sản xuất", "year"), ("Số km", "mileage")):
                expect(main.get_by_role("spinbutton", name=label)).to_have_value(str(vehicle[field]))
            for label, field in (("Bảo dưỡng hãng", "dealer_service"), ("Từng chạy dịch vụ", "commercial"),
                                 ("Từng ngập nước", "flood"), ("Tai nạn nặng", "major_accident")):
                expect(main.get_by_role("checkbox", name=label)).to_be_checked(checked=vehicle[field])

        def fill(label, value):
            field = main.get_by_role("spinbutton", name=label)
            field.fill(str(value))
            field.press("Enter")
            expect(field).to_have_value(str(value))

        def metric(label, expected):
            item = main.locator(".metric-card").filter(has=page.get_by_text(label, exact=True)).locator(".value")
            expect(item).to_have_text(expected)

        def result_for(code):
            button("Định giá").click()
            expect(main.get_by_text("Kết quả tóm tắt", exact=True)).to_be_visible()
            expected = demos[code]["valuation"]
            metric("Giá đề xuất", f"{vi(expected['price'])} triệu ₫")
            button("Xem kết quả và giải thích").click()
            expect(main.get_by_role("heading", name=title(code))).to_be_visible()
            metric("Giá đề xuất", f"{vi(expected['price'])} triệu ₫")
            metric("Giá theo luật", f"{vi(expected['inference']['price'])} triệu ₫")
            metric("Giá CBR", f"{vi(expected['cbr']['price'])} triệu ₫" if expected["cbr"]["price"] is not None else "—")
            metric("Mức tin cậy", expected["confidence"])
            for key in ("lower", "price", "upper"):
                expect(main.locator(".annotation-text").get_by_text(vi(expected[key]), exact=True).first).to_be_visible()
            return expected

        def title(code):
            frame = demos[code]["frame"]
            return " ".join(frame[field] for field in ("brand", "model", "name"))

        def shot(name, bottom):
            expect(bottom).to_be_visible()
            page.evaluate("document.fonts.ready")
            page.evaluate("document.querySelector('[data-testid=stMain]').scrollTop = 0")
            expect(page.get_by_test_id("stException")).to_have_count(0)
            assert main.evaluate("(node) => node.scrollWidth <= node.clientWidth + 2"), name
            assert main.locator(".table-wrap:visible").evaluate_all(
                "(tables) => tables.every((table) => table.scrollWidth <= table.clientWidth + 2)"
            ), name
            box = bottom.bounding_box()
            assert box is not None and box["y"] >= 0, name
            height = round(box["y"] + box["height"] + 24)
            assert height <= HEIGHT, f"{name}: vùng chụp cao {height} px, vượt {HEIGHT} px."
            page.screenshot(path=OUTPUT / name, clip={"x": 0, "y": 0, "width": WIDTH, "height": height},
                            animations="disabled")
            images.append({"file": name, "width": WIDTH, "height": height})
            print(f"Đã chụp {name} ({WIDTH} × {height}).", flush=True)

        page.goto(url, wait_until="domcontentloaded")
        expect(main.get_by_role("heading", name="Định giá ô tô cũ")).to_be_visible()
        go("Kết quả và giải thích")
        expect(main.get_by_text("Định giá một xe để xem", exact=False)).to_be_visible()
        main.get_by_role("link", name=re.compile("Quay về form định giá$")).click()
        selected("Phiên bản", "1.5G CVT")
        expect(main.get_by_role("spinbutton", name="Số km")).to_have_value("95000")
        shot("01_form_nhap_xe.png", button("Định giá"))
        checks.append({"case": "Mở kết quả khi chưa tính", "observed": "Hiện hướng dẫn và quay lại form."})

        select("Hãng", "Honda")
        selected("Dòng", "City")
        selected("Phiên bản", "1.5 L")
        select("Dòng", "Civic")
        selected("Phiên bản", "1.5 G")
        select("Phiên bản", "1.5 RS")
        selected("Phiên bản", "1.5 RS")
        checks.append({"case": "Danh sách hãng, dòng, phiên bản", "observed": "Honda cập nhật City. Civic cập nhật 1.5 G và cho chọn 1.5 RS."})

        choose_demo("dealer")
        choose_demo("normal")
        fill("Năm sản xuất", 2027)
        fill("Số km", -1)
        button("Định giá").click()
        expect(main.get_by_text(re.compile("Năm sản xuất phải.*Số km phải"))).to_be_visible()
        fill("Năm sản xuất", 2019)
        fill("Số km", 95000)
        checks.append({"case": "Năm 2027 và số km âm", "observed": "Hiện cả hai lỗi miền giá trị bằng tiếng Việt."})

        normal = result_for("normal")
        chart = main.get_by_test_id("stPlotlyChart")
        shot("02_ket_qua_va_khoang_gia.png", chart.first)
        formula = main.locator(".formula")
        expect(formula).to_contain_text(f"{pct(normal['cbr_weight'], 2)} × {vi(normal['cbr']['price'], 2)}")
        shot("03_giai_thich_gia.png", main.get_by_text("Tin cậy cao", exact=False))
        main.get_by_role("tab", name="Vết suy diễn").click()
        expect(main.locator("table:visible")).to_contain_text("TUOI-04")
        shot("04_vet_suy_dien.png", main.get_by_text("Các tỷ lệ tính trên giá", exact=False))
        main.get_by_role("tab", name="Xe tương tự").click()
        expect(main.locator("table:visible tbody tr")).to_have_count(5)
        for neighbor in normal["cbr"]["neighbors"]:
            row = main.get_by_role("row", name=re.compile(neighbor["case"]["case_id"]))
            expect(row).to_contain_text(vi(neighbor["adjusted_price"], 2))
        shot("05_xe_tuong_tu.png", main.get_by_text("Cách tính độ tương tự và hiệu chỉnh", exact=True))
        checks.append({"case": "Kết quả Vios, công thức, khoảng và truy hồi",
                       "observed": f"Giá {vi(normal['price'])} triệu đồng, ba nhãn khoảng và giá hiệu chỉnh 5 xe khớp JSON."})

        go("Phân tích dữ liệu")
        expect(main.get_by_role("heading", name="Phân tích dữ liệu")).to_be_visible()
        metric("Số mẫu", vi(preparation["train"], 0))
        expect(main.get_by_test_id("stPlotlyChart")).to_have_count(3)
        shot("06_phan_tich_du_lieu.png", main.get_by_test_id("stPlotlyChart").last)
        select("Hãng", "Toyota")
        expect(main.get_by_text(vi(preparation["train"], 0), exact=True)).to_have_count(0)
        select("Phân khúc", "Hatchback hạng A")
        expect(main.get_by_text("Bộ lọc hiện tại không có xe phù hợp.")).to_be_visible()
        checks.append({"case": "Bộ lọc phân tích dữ liệu", "observed": "Toyota thay đổi số mẫu. Ghép Hatchback hạng A hiện trạng thái rỗng."})

        go("Quản trị tri thức")
        expect(main.get_by_role("heading", name="Quản trị tri thức")).to_be_visible()
        metric("Kiểm tra nhất quán", "Hợp lệ")
        shot("07_quan_tri_tri_thuc.png", main.get_by_test_id("stDataFrame").first)
        main.get_by_role("tab", name="Khung xe", exact=True).click()
        expect(main.get_by_text("Hãng → dòng → phiên bản", exact=True)).to_be_visible()
        main.get_by_role("tab", name="Kho tình huống", exact=True).click()
        expect(main.get_by_text("Kho tình huống train", exact=True)).to_be_visible()
        main.get_by_role("tab", name="Kiểm tra nhất quán", exact=True).click()
        expect(main.get_by_text("Mã duy nhất, điều kiện và hành động hợp lệ.", exact=False)).to_be_visible()
        checks.append({"case": "Quản trị tri thức", "observed": "Mở đủ bốn tab. Dữ liệu hiện tại đạt kiểm tra nhất quán."})

        go("Kết quả và giải thích")
        metric("Giá đề xuất", f"{vi(normal['price'])} triệu ₫")
        go("Định giá")
        fill("Số km", 96000)
        expect(main.get_by_text("Cần định giá lại", exact=False)).to_be_visible()
        go("Kết quả và giải thích")
        expect(main.get_by_text("Đang hiển thị lần tính trước", exact=False)).to_be_visible()
        go("Định giá")
        expect(main.get_by_role("spinbutton", name="Số km")).to_have_value("96000")
        button("Nạp mẫu").click()
        expect(main.get_by_role("spinbutton", name="Số km")).to_have_value("95000")
        checks.append({"case": "Kết quả và đầu vào qua các trang",
                       "observed": "Giữ kết quả và báo khi sửa km. Nạp lại mẫu khôi phục 95.000 km."})

        choose_demo("flood")
        result_for("flood")
        alert = main.get_by_role("alert").filter(has_text="Cảnh báo lịch sử xe")
        expect(alert).to_contain_text("Xe từng ngập nước.")
        shot("08_canh_bao_ngap_nuoc.png", main.get_by_text("Tin cậy thấp", exact=False))
        checks.append({"case": "Ngập nước", "observed": "Có cảnh báo lịch sử, khoảng giá và tin cậy thấp."})

        go("Định giá")
        choose_demo("sparse")
        sparse = result_for("sparse")
        expect(main.get_by_text("Chỉ có 0 xe đạt ngưỡng", exact=False).first).to_be_visible()
        assert sparse["price"] == sparse["inference"]["price"]
        checks.append({"case": "Không có CBR", "observed": "Giá đề xuất bằng giá theo luật, hiện lý do 0 xe đạt ngưỡng."})

        go("Định giá")
        choose_demo("commercial")
        result_for("commercial")
        expect(main.get_by_text("Xe từng chạy dịch vụ.", exact=False).first).to_be_visible()
        go("Định giá")
        choose_demo("dealer")
        result_for("dealer")
        main.get_by_role("tab", name="Vết suy diễn").click()
        expect(main.locator("table:visible")).to_contain_text("BD-01")
        checks.append({"case": "Dịch vụ và bảo dưỡng hãng", "observed": "Ca dịch vụ có cảnh báo. Ca bảo dưỡng kích hoạt BD-01."})

        go("Định giá")
        choose_demo("normal")
        for flag in ("Từng chạy dịch vụ", "Từng ngập nước", "Tai nạn nặng"):
            main.get_by_text(flag, exact=True).click()
            expect(main.get_by_role("checkbox", name=flag)).to_be_checked()
        button("Định giá").click()
        button("Xem kết quả và giải thích").click()
        alert = main.get_by_role("alert").filter(has_text="Cảnh báo lịch sử xe")
        expect(alert.locator("p")).to_have_count(4)
        main.get_by_role("tab", name="Vết suy diễn").click()
        expect(main.locator("table:visible")).to_contain_text("RR-04")
        checks.append({"case": "Ba rủi ro cùng lúc", "observed": "Hiện ba cảnh báo, vết suy diễn có RR-04 chặn hệ số rủi ro."})
        assert not page_errors, page_errors
        browser_version = browser.version
        browser.close()

    result = {"browser": f"Chromium {browser_version}", "viewport": [WIDTH, HEIGHT], "passed": len(checks),
              "checks": checks, "screenshots": images}
    (OUTPUT / "browser_checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(checks)} ca UI đạt. Đã lưu 8 ảnh và browser_checks.json.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8501", help="Địa chỉ app đang chạy")
    parser.add_argument("--chromium", help="Dùng Chromium có sẵn thay cho bản do Playwright quản lý")
    args = parser.parse_args()
    capture(args.url, args.chromium)


if __name__ == "__main__":
    main()
