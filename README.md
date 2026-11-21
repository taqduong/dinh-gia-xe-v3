# Hệ hỗ trợ quyết định định giá ô tô cũ

**Công nghệ tri thức · Nhóm 4 · Đại học Công nghiệp Hà Nội**

Ứng dụng tiếng Việt dùng Streamlit và Plotly. Máy suy diễn tiến định giá theo luật, CBR truy hồi và hiệu chỉnh giá xe tương tự, còn hệ lai tổng hợp hai kết quả và giải thích khoảng tham khảo.

**Dữ liệu mô phỏng.** Giá xe mới, hệ số khấu hao, mức ảnh hưởng của lịch sử xe, cấu hình CBR và các ngưỡng tin cậy đều là giả định. Giá trong bộ dữ liệu do một mô hình sinh với nhiễu tạo ra.

## Chạy trên Windows với VS Code

Cài Python 3.12, Git và VS Code. Clone nhánh `main`, mở thư mục dự án bằng VS Code và chọn **Terminal → New Terminal**. Chạy trong PowerShell.

~~~powershell
git clone --branch main https://github.com/taqduong/dinh-gia-xe-v3.git
cd dinh-gia-xe-v3
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
~~~

Mở [localhost:8501](http://localhost:8501). Để VS Code dùng đúng môi trường, mở Command Palette, chọn **Python: Select Interpreter** và chọn `.venv\Scripts\python.exe`. Dừng app bằng `Ctrl+C` trong terminal. Trên macOS hoặc Linux, dùng `python3.12 -m venv .venv` và thay `.\.venv\Scripts\python.exe` bằng `.venv/bin/python`.

## Demo nhanh

Tại **Định giá**, chọn mẫu, bấm **Định giá**, sau đó bấm **Xem kết quả và giải thích**. Tab **Vết suy diễn** có waterfall và giá trước/sau từng luật. Tab **Xe tương tự** có tối đa 5 xe với giá gốc, giá hiệu chỉnh và điểm tương tự. Khi sửa đầu vào, biểu mẫu báo cần tính lại. Trang kết quả giữ lần tính gần nhất trong phiên và đánh dấu khi đầu vào đã đổi.

| Mẫu | Xe và điều kiện | Giá đề xuất (triệu đ) | Tin cậy |
|---|---|---:|---|
| Xe bình thường | Toyota Vios 1.5G CVT 2019, 95.000 km, Hà Nội, Khá | 358,3 | Cao |
| Xe bảo dưỡng hãng | Vios như trên, bật cờ bảo dưỡng hãng | 353,7 | Cao |
| Xe ngập nước | Vios 2019, 95.000 km, Trung bình, bật cờ ngập nước | 221,7 | Thấp |
| Xe chạy dịch vụ | Vios 2019, 155.000 km, bật cờ chạy dịch vụ | 273,9 | Trung bình |
| Xe thiếu tình huống tương tự | Lexus RX 350 Luxury 2021, 50.000 km | 2.507,4 | Thấp |

Ở ca chính, giá mới 548 triệu đồng đi qua 5 luật cho giá 328,0 triệu đồng. Giá CBR từ 5 xe là 369,8 triệu đồng, chiếm 72,46% phép tổng hợp. Khoảng tham khảo là **303,8–412,9 triệu đồng**. Với mẫu bảo dưỡng hãng, giá theo luật tăng, còn tập xe truy hồi thay đổi khiến giá lai giảm trong ca này. Chi tiết từng phép tính có trong chương 3 của báo cáo và [vết demo JSON](outputs/experiments/demo_results.json).

## Các mô-đun

| Nơi lưu | Nội dung |
|---|---|
| `app.py`, `src/ui.py`, `src/charts.py` | Điểm vào, bốn trang Streamlit và biểu đồ Plotly |
| `kb/`, `src/knowledge.py` | Khung hãng → dòng → phiên bản, 25 luật, cấu hình, 5 mẫu và kiểm tra nhất quán |
| `src/inference.py`, `src/cbr.py`, `src/pricing.py` | Suy diễn tiến, truy hồi và hiệu chỉnh, tổng hợp và khoảng giá |
| `src/experiment.py`, `scripts/` | Sinh dữ liệu, làm sạch, chia tập, thực nghiệm và dựng báo cáo |
| `tests/`, `outputs/screenshots/capture.py` | Pytest và bài kiểm tra ứng dụng trên Chromium |
| `data/`, `outputs/` | Dữ liệu, số liệu thực nghiệm, ảnh chụp và báo cáo |

### Cách định giá

- Máy suy diễn so khớp tiền đề sau từng lần cập nhật. Ưu tiên cao chạy trước, bằng nhau thì xét theo mã luật. Mỗi luật chạy tối đa một lần. Các hệ số rủi ro nhân lần lượt. Khi có ít nhất hai rủi ro, RR-04 giữ hệ số gộp tối thiểu 0,58 và hệ thống giữ tất cả cảnh báo.
- CBR lọc xe cùng dòng, cùng cờ ngập nước/tai nạn nặng và chênh không quá 4 đời. Điểm là tổng có trọng số của phiên bản 22%, năm 20%, km 18%, khu vực 8%, tình trạng 14%, bảo dưỡng hãng 8% và dịch vụ 10%. Chọn tối đa 5 xe đạt 0,72 trở lên. Hiệu chỉnh giá gốc bằng tỷ số giá mới và chênh lệch đời, km, tình trạng, bảo dưỡng, dịch vụ, vùng. Sau đó lấy trung bình giá hiệu chỉnh với trọng số là độ tương tự.
- Khi có ít nhất 2 xe đạt ngưỡng, trọng số CBR bằng `0,25 + 0,50 × điểm trung bình × số xe / 5`. Nhân thêm 0,80 nếu có ngập nước hoặc tai nạn nặng. Tỷ trọng còn lại dành cho luật. Khi thiếu xe, giá đề xuất bằng giá luật và giao diện nêu lý do.
- Khoảng gồm biên cơ sở theo chất lượng chứng cứ, cộng phần chênh giữa hai giá và phần phân tán của giá xe hiệu chỉnh. Các ngưỡng và hệ số nằm trong [settings.json](kb/settings.json).

## Dữ liệu mô phỏng và thực nghiệm

Bộ sinh cố định **seed 4126** và **năm tham chiếu 2026**. Bộ sinh lấy mẫu theo độ phổ biến giả định, lấy tuổi theo phân bố tam giác, tính số km theo tuổi và cờ dịch vụ, rồi sinh tình trạng từ mức hao mòn có nhiễu. Giá mô phỏng phụ thuộc giá mới, đường khấu hao liên tục, số km, vùng, tình trạng, lịch sử và nhiễu log-normal. Lexus RX có trong danh mục nhưng được dành cho demo thiếu đối chứng nên không có trong kho sinh.

| Trường CSV | Ý nghĩa |
|---|---|
| `case_id`, `frame_id` | Mã xe mô phỏng và mã phiên bản |
| `year`, `mileage` | Năm sản xuất và số km tích lũy |
| `region`, `condition` | Khu vực và mức tình trạng |
| `dealer_service`, `commercial`, `flood`, `major_accident` | Bốn cờ Có/Không |
| `price` | Giá mô phỏng, triệu đồng |

[Raw](data/raw.csv) có 3.040 dòng, gồm 24 dòng trùng và 16 dòng lỗi được chèn chủ đích. [Nhật ký làm sạch](data/preparation.json) ghi số dòng trước và sau từng bước. Sau làm sạch còn 3.000 dòng, chia [2.400 train](data/train.csv) và [600 test](data/test.csv). Chỉ train được dùng để lập kho CBR và fit Random Forest. Tham số được ấn định trước, tập test dùng cho đánh giá.

### Kết quả lần chạy bàn giao

Sai số và R² được so trên **565 xe có giá CBR**. CBR thiếu 35 trên 600 xe. Giá CBR ở các ca thiếu được để trống trong bảng dự đoán. Hệ lai trả giá luật cho 35 ca đó. Thời gian đo dự đoán trên đủ 600 lượt, RF chạy theo lô, tách thời gian fit và nạp dữ liệu.

| Phương pháp | MAE (triệu đ) | MAPE (%) | R² |
|---|---:|---:|---:|
| Chỉ luật | 37,34 | 8,65 | 0,9319 |
| Chỉ CBR | **25,47** | **5,92** | **0,9652** |
| Random Forest | 27,25 | 6,25 | 0,9604 |
| Hệ lai | 26,41 | 6,07 | 0,9636 |

Trên toàn bộ 600 xe, MAE của hệ lai là **26,64 triệu đồng**. Khoảng của hệ lai phủ **548/600 ca (91,33%)**, rộng trung bình **124,61 triệu đồng**. Đây là số liệu trên cùng bộ sinh mô phỏng. Hiệu năng trên thị trường cần được đo với dữ liệu giao dịch thực tế.

- [Dự đoán CSV](outputs/experiments/predictions.csv) · [Chỉ số CSV](outputs/experiments/metrics.csv) · [Chỉ số và thời gian JSON](outputs/experiments/metrics.json)
- [Biểu đồ sai số](outputs/experiments/errors.png) · [Biểu đồ khoảng giá](outputs/experiments/intervals.png)

### Tái lập trên Windows

Chạy từ thư mục gốc. Lần chạy mới ghi đè các tệp đầu ra tương ứng. Sai số có thể đối chiếu theo seed và phiên bản thư viện. Thời gian thay đổi theo máy và từng lần chạy.

~~~powershell
.\.venv\Scripts\python.exe -m scripts.generate_data
.\.venv\Scripts\python.exe -m scripts.prepare_data
.\.venv\Scripts\python.exe -m scripts.run_experiments
.\.venv\Scripts\python.exe -m pytest -q --junitxml=outputs/test-results.xml
~~~

Mở app ở terminal thứ nhất. Ở terminal thứ hai, cài Chromium của Playwright rồi chạy script chụp ảnh. Có thể truyền `--chromium` để dùng đường dẫn tới Chromium cài sẵn.

~~~powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m outputs.screenshots.capture --url http://127.0.0.1:8501
.\.venv\Scripts\python.exe -m scripts.build_report --junit outputs/test-results.xml
~~~

Thêm `--pdf` khi đã cài LibreOffice. Nếu `soffice` chưa có trong PATH, truyền `--soffice "C:\Program Files\LibreOffice\program\soffice.exe"` hoặc mở tệp DOCX và xuất PDF trong Word.

## Ảnh chụp, kiểm thử và báo cáo

- [Báo cáo Word chỉnh sửa được](outputs/report/bao_cao_dinh_gia_xe_cu.docx) · [Báo cáo PDF](outputs/report/bao_cao_dinh_gia_xe_cu.pdf) · [Script dựng báo cáo](scripts/build_report.py)
- Pytest đạt 20 ca. [Playwright đạt 11 ca](outputs/screenshots/browser_checks.json) trên Chromium ở 1.440 px. [Script chụp và kiểm tra](outputs/screenshots/capture.py)

| Ảnh | Màn hình |
|---|---|
| [01](outputs/screenshots/01_form_nhap_xe.png) | Biểu mẫu ca Vios |
| [02](outputs/screenshots/02_ket_qua_va_khoang_gia.png) | Kết quả và thanh khoảng giá |
| [03](outputs/screenshots/03_giai_thich_gia.png) | Phép tổng hợp giá |
| [04](outputs/screenshots/04_vet_suy_dien.png) | Waterfall và bảng vết suy diễn |
| [05](outputs/screenshots/05_xe_tuong_tu.png) | Năm xe gần nhất và giá hiệu chỉnh |
| [06](outputs/screenshots/06_phan_tich_du_lieu.png) | Bộ lọc và các biểu đồ dữ liệu |
| [07](outputs/screenshots/07_quan_tri_tri_thuc.png) | Tập luật và trạng thái kiểm tra |
| [08](outputs/screenshots/08_canh_bao_ngap_nuoc.png) | Cảnh báo ngập nước |
