# DỰ ÁN: askDataAI — PROJECT PROPOSAL

---

## 1. Tổng quan dự án

**askDataAI** là một **AI-powered Text-to-SQL platform** cho phép người dùng hỏi câu hỏi bằng ngôn ngữ tự nhiên (tiếng Việt/Anh) và nhận kết quả truy vấn SQL tự động, cùng biểu đồ trực quan hóa dữ liệu.

- **Đối tượng**: Doanh nghiệp vừa và nhỏ, nhân viên kinh doanh, quản lý
- **Vấn đề giải quyết**: Người dùng không biết SQL vẫn có thể khai thác dữ liệu
- **Data Source**: Microsoft SQL Server (mở rộng sang MySQL, PostgreSQL trong tương lai)

---

## 2. Tính năng hiện tại

### 2.1 Text-to-SQL Pipeline (14 stages)

| Tính năng | Mô tả |
|-----------|-------|
| Phân tích ý định | Phân loại câu hỏi: truy vấn dữ liệu / khám phá schema / hội thoại |
| Schema Retrieval | Tìm kiếm vector để xác định bảng/cột liên quan |
| Schema Linking | LLM ánh xạ entity trong câu hỏi → bảng/cột cụ thể |
| Column Pruning | Loại bỏ cột không liên quan, giảm context window |
| CoT Reasoning | Chain-of-Thought: lập kế hoạch SQL trước khi viết |
| SQL Generation | Sinh SQL từ context đã xử lý |
| SQL Correction | Tự động sửa lỗi SQL (tối đa 3 lần retry) |
| SQL Guardian | Bảo vệ: chống injection, read-only, column masking |
| Business Glossary | Ánh xạ thuật ngữ nghiệp vụ (VD: "doanh thu" = SUM(SalesAmount)) |
| Semantic Memory | Học từ các truy vấn thành công trước đó |

### 2.2 Chart Generation (Vega-Lite)

- Tự động sinh biểu đồ phù hợp từ kết quả SQL
- Hỗ trợ: Bar, Grouped Bar, Stacked Bar, Line, Multi-line, Area, Pie
- LLM chọn loại biểu đồ tối ưu dựa trên dữ liệu

### 2.3 Web Interface

- Chat UI: hỏi đáp dạng hội thoại
- ERD Modeling: xem sơ đồ quan hệ các bảng
- Settings: bật/tắt pipeline features, điều chỉnh tham số
- Debug Trace: xem chi tiết từng stage pipeline (dành cho dev)

### 2.4 Docker Deployment

- Đóng gói bằng Docker Compose (Backend + Frontend)
- Tự động resolve localhost khi chạy trong Docker
- Volume persistence cho ChromaDB và semantic memory

---

## 3. Tính năng sắp tới (Roadmap)

###  3.1 AI Auto-Description (Phase tiếp theo)

**Vấn đề:** Khi kết nối database mới, các bảng và cột thường không có mô tả (description). Điều này khiến LLM khó hiểu ngữ cảnh → sinh SQL sai.

**Giải pháp:** Sử dụng AI để **tự động sinh description** cho các cột và bảng:

1. **Input**: Người dùng mô tả một vài bảng/cột mẫu (seed descriptions)
2. **AI Analysis**: LLM phân tích tên bảng, tên cột, kiểu dữ liệu, dữ liệu mẫu
3. **Auto-Generate**: Tự động sinh description cho toàn bộ bảng/cột còn lại
4. **Human Review**: Người dùng review và chỉnh sửa các description được sinh

**Ví dụ:**
```
Input (seed):
  - DimCustomer.FirstName → "Tên khách hàng"
  - DimCustomer.CustomerKey → "Mã định danh khách hàng (PK)"

AI Generated:
  - DimCustomer.LastName → "Họ khách hàng"
  - DimCustomer.EmailAddress → "Địa chỉ email khách hàng"
  - DimCustomer.BirthDate → "Ngày sinh khách hàng"
  - FactInternetSales.SalesAmount → "Doanh thu bán hàng qua internet"
  - DimGeography.City → "Thành phố trong phân vùng địa lý"
```

**Lợi ích:**
- Giảm **80-90%** thời gian setup modeling metadata
- Tăng độ chính xác SQL generation nhờ context tốt hơn
- Phù hợp cho doanh nghiệp có nhiều bảng (50-200+)

### 3.2 Các tính năng khác (dự kiến)

| Tính năng | Mô tả | Ưu tiên |
|-----------|-------|---------|
| Multi-datasource | Hỗ trợ MySQL, PostgreSQL | Cao |
| Export Report | Xuất PDF/Excel từ kết quả | Trung bình |
| Scheduled Queries | Tự động chạy query theo lịch | Thấp |
| Role-based Access | Phân quyền theo vai trò | Cao |
| Dashboard Builder | Tạo dashboard từ nhiều charts | Trung bình |

---

## 4. Kiến trúc hệ thống

```
┌─────────────────────┐
│   Browser (User)    │
│   localhost:3000     │
└─────────┬───────────┘
          │
┌─────────▼───────────┐     ┌──────────────────┐
│   Next.js Frontend  │────▶│  FastAPI Backend  │
│   React 19 + Antd 6 │     │  Python 3.11     │
│   Vega-Lite Charts  │     │  14-stage pipe   │
└─────────────────────┘     └───────┬──────────┘
                                    │
                        ┌───────────┼───────────┐
                        │           │           │
                 ┌──────▼──┐  ┌────▼────┐  ┌───▼──────┐
                 │ ChromaDB │  │   LLM   │  │SQL Server│
                 │ (Vector) │  │ (GPT-4) │  │ (Data)   │
                 └──────────┘  └─────────┘  └──────────┘
```

---

## 5. Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, React 19, Ant Design 6, Vega-Lite |
| Backend | Python 3.11, FastAPI, SQLAlchemy |
| Vector DB | ChromaDB|
| Database | Microsoft SQL Server |
| Deployment | Docker Compose |

---

## 6. Thành viên phát triển

- **Nguyễn Quang Chiến** — Đại học Bách Khoa Đà Nẵng
- **Nguyễn Hòa Thuận** — Đại học Bách Khoa Đà Nẵng
- **Trương Quang Vinh** — Đại học Bách Khoa Đà Nẵng

---

