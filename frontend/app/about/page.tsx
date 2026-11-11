import { Badge, PageHeader, Panel } from "@/components/ui";

/* Team info mirrors README.md ("Thành Viên Nhóm") and AGENTS.md §4 (ownership). */
const PROJECT_TITLE =
  "Nghiên cứu quy trình phát triển phần mềm Agile và các kỹ thuật học máy hiện đại ứng dụng trong phát triển thử nghiệm hệ thống thông tin hỗ trợ thu thập, phân tích và dự báo giá cổ phiếu và tiền số";

const SUPERVISOR = "ThS. Nguyễn Đình Thái";
const FACULTY = "Khoa CNS - Trường Đại học Điện lực";

const MEMBERS = [
  { name: "Đỗ Quang Hà", studentId: "23810310132", className: "D18CNPM2", leader: true, work: "Mô hình ARIMA" },
  { name: "Nguyễn Văn Kiên", studentId: "23810310138", className: "D18CNPM2", leader: false, work: "Mô hình XGBoost" },
  { name: "Khiếu Đình Trung Nguyên", studentId: "24810310401", className: "D19CNPM4", leader: false, work: "Frontend" },
  { name: "Nguyễn Trọng Đại", studentId: "23810310120", className: "D18CNPM2", leader: false, work: "Mô hình GRU" },
  { name: "Lê Hải Nam", studentId: "23810310377", className: "D18CNPM5", leader: false, work: "Mô hình Random Forest" },
  { name: "Nguyễn Trọng Hiếu", studentId: "24810340513", className: "D19CNPM1", leader: false, work: "Frontend" },
];

const STACK = [
  { part: "Thu thập dữ liệu", tech: "Python 3.11 + FastAPI, Celery & Redis; nguồn cổ phiếu VN và Binance" },
  { part: "Lưu trữ", tech: "PostgreSQL 16 + TimescaleDB" },
  { part: "Mô hình dự báo", tech: "ARIMA, XGBoost, Random Forest, GRU (PyTorch); Optuna, MLflow" },
  { part: "Giải thích mô hình", tech: "SHAP" },
  { part: "Giao diện", tech: "Next.js (TypeScript) + Apache ECharts" },
];

export default function AboutPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Giới thiệu"
        description="Thông tin về đề tài nghiên cứu khoa học và nhóm thực hiện."
      />

      <Panel title="Đề tài">
        <p className="text-sm leading-relaxed text-slate-200">{PROJECT_TITLE}</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-slate-400">Đơn vị</dt>
            <dd className="font-semibold text-white">{FACULTY}</dd>
          </div>
          <div>
            <dt className="text-slate-400">Giảng viên hướng dẫn</dt>
            <dd className="font-semibold text-white">{SUPERVISOR}</dd>
          </div>
        </dl>
      </Panel>

      <Panel title="Thành viên nhóm" subtitle={`${MEMBERS.length} sinh viên`} bodyClassName="overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>STT</th>
              <th>Họ và tên</th>
              <th>Mã sinh viên</th>
              <th>Lớp</th>
              <th>Phụ trách</th>
            </tr>
          </thead>
          <tbody>
            {MEMBERS.map((member, index) => (
              <tr key={member.studentId}>
                <td>{index + 1}</td>
                <td className="font-semibold text-white">
                  {member.name} {member.leader && <Badge tone="amber">Chủ nhiệm đề tài</Badge>}
                </td>
                <td className="font-mono text-xs">{member.studentId}</td>
                <td>{member.className}</td>
                <td className="text-slate-300">{member.work}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="Hệ thống" subtitle="Thu thập, phân tích trực quan và dự báo giá cổ phiếu Việt Nam và tiền mã hóa" bodyClassName="overflow-x-auto">
        <table className="data-table">
          <tbody>
            {STACK.map((row) => (
              <tr key={row.part}>
                <td className="font-semibold text-white">{row.part}</td>
                <td className="text-slate-300">{row.tech}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}
