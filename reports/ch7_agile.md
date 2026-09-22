# Chương 7. Quy trình Agile & Quản lý dự án

Chương này giải quyết câu hỏi nghiên cứu RQ4: *"Quy trình Agile và hệ thống CI/CD ảnh hưởng như thế nào đến khả năng kiểm soát rủi ro trong một dự án có thành phần AI?"*

## 7.1. Phân tích định tính: Giá trị của Agile và CI/CD

Quá trình vận hành 12 sprint đã chứng minh giá trị của quy trình Agile trong việc quản trị rủi ro kỹ thuật, thể hiện qua hai khía cạnh cốt lõi:

**1. Phân rã công việc linh hoạt theo đặc thù mô hình:**
Ban đầu, nhóm dự định chia việc theo tầng kỹ thuật (Frontend, Backend, AI). Tuy nhiên, đặc thù của MLOps đòi hỏi sự liền mạch từ dữ liệu đến serving. Nhóm đã áp dụng Agile để điều chỉnh linh hoạt (từ Sprint 4): chia task theo từng cụm mô hình (ARIMA, XGBoost, Random Forest, GRU). Hệ quả là 4 thành viên có thể làm việc song song, độc lập phát triển pipeline đặc trưng và entrypoint huấn luyện của riêng mình mà không gây xung đột (merge conflict) mã nguồn.

**2. Cổng chất lượng CI/CD (Quality Gates):**
Khác với các dự án học thuật thông thường, hệ thống cưỡng chế chất lượng bằng CI (GitHub Actions) thay vì niềm tin. Tính năng Branch Protection đã chặn đứng hàng chục lượt đẩy code có lỗi cú pháp hoặc hỏng test. Nhờ vậy, nhánh `main` và `develop` luôn duy trì trạng thái có thể triển khai (deployable) bất cứ lúc nào.

## 7.2. Các khoảng trống quy trình và Nợ kỹ thuật

Một nguyên tắc của Agile là minh bạch. Báo cáo ghi nhận những sai lệch quy trình thực tế đã xảy ra và đang được khắc phục:

**1. Hiện tượng thắt cổ chai commit:**
Kiểm tra lịch sử Git cho thấy mật độ commit đang bị tập trung cục bộ vào một vài tài khoản (do thói quen code chung trên một máy trạm hoặc gửi file rời rạc cho trưởng nhóm commit hộ). Điều này đi ngược lại nguyên tắc của Agile và làm giảm khả năng truy vết trách nhiệm mã nguồn của từng cá nhân.

**2. Vi phạm quy tắc Code Review (Sự cố PR #44 và #45):**
Quy tắc CODEOWNERS bắt buộc phải có ít nhất 1 người review trước khi merge. Tuy nhiên, do áp lực tiến độ trước đợt kiểm thử ngày 16/09, PR #44 (sửa lỗi mount volume mlflow) và PR #45 (sửa kiến trúc GRU v2) đã bị ép merge (force merge) bởi tài khoản admin khi chưa có người thứ hai đánh giá. Lỗi này để lại rủi ro tiềm ẩn chưa được kiểm chứng chéo.

**Đề xuất khắc phục cho giai đoạn cuối:**
- Siết chặt lại quy tắc bảo vệ nhánh: tắt hoàn toàn quyền bypass quy định review của tài khoản admin trên GitHub.
- Yêu cầu các thành viên tự commit và push code từ máy cá nhân thông qua token định danh rõ ràng trong 5 tuần cuối.