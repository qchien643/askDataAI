# 📖 askDataAI — TỔNG QUAN DỰ ÁN & PIPELINE
### Tài liệu dành cho thiết kế slide thuyết trình

---

## MỤC LỤC

1. [Dự án là gì?](#1-dự-án-là-gì)
2. [Vấn đề giải quyết](#2-vấn-đề-giải-quyết)
3. [Demo Flow](#3-demo-flow)
4. [Pipeline chi tiết (14 stages)](#4-pipeline-chi-tiết)
5. [Chart Generation](#5-chart-generation)
6. [Kiến trúc kỹ thuật](#6-kiến-trúc-kỹ-thuật)
7. [Tính năng sắp tới: AI Auto-Description](#7-tính-năng-sắp-tới)
8. [Gợi ý slide](#8-gợi-ý-slide)

---

## 1. Dự án là gì?

**askDataAI** là một chatbot AI giúp người dùng **hỏi câu hỏi về dữ liệu bằng tiếng Việt** và nhận kết quả ngay lập tức — không cần biết SQL.

**Một câu hỏi đơn giản:**
> "Top 5 sản phẩm có doanh thu cao nhất năm 2024"

**Hệ thống sẽ:**
1. Hiểu ý định → tìm bảng phù hợp → sinh SQL
2. Chạy SQL → trả bảng kết quả
3. Tạo biểu đồ trực quan tự động

---

## 2. Vấn đề giải quyết

### Thực trạng

| Cách truyền thống | Với askDataAI |
|-------------------|-----------------|
| Cần biết SQL | Chỉ cần biết hỏi |
| Cần hiểu cấu trúc DB | AI tự tìm bảng/cột |
| Mất 5-30 phút viết query | Kết quả trong 10 giây |
| Chỉ IT/analyst dùng được | Ai cũng dùng được |
| Phải mở SSMS/tool DB | Dùng trình duyệt web |

### Đối tượng sử dụng
- 👔 **Quản lý kinh doanh**: xem doanh thu, báo cáo
- 📊 **Nhân viên phân tích**: truy vấn nhanh không cần IT
- 🏪 **Chủ cửa hàng nhỏ**: khai thác dữ liệu từ hệ thống sẵn có

---

## 3. Demo Flow

```
┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│  Người dùng  │    │   Mini Wren    │    │   Database   │
│  hỏi câu hỏi │───▶│   AI xử lý    │───▶│  chạy SQL    │
│  bằng TV     │    │   14 bước      │    │  trả kết quả │
└──────────────┘    └────────────────┘    └──────┬───────┘
                                                  │
                    ┌────────────────┐            │
                    │  Hiển thị      │◀───────────┘
                    │  bảng + biểu đồ│
                    └────────────────┘
```

**Ví dụ thực tế:**

| Câu hỏi (tiếng Việt) | SQL được sinh ra |
|----------------------|-----------------|
| "Doanh thu tháng 3" | `SELECT SUM(SalesAmount) FROM FactInternetSales WHERE MONTH(OrderDate)=3` |
| "Top khách hàng VIP" | `SELECT TOP 10 c.FirstName, SUM(s.SalesAmount) AS Revenue FROM ...` |
| "So sánh sản phẩm theo vùng" | `SELECT g.Region, p.ProductName, SUM(...) FROM ... GROUP BY ...` |

---

## 4. Pipeline chi tiết

Pipeline xử lý gồm **14 bước**, chia thành 5 giai đoạn chính:

### 🔴 Giai đoạn 1: Tiền xử lý (Bước 1-2)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 1 | **PreFilter** | Lọc câu hỏi nguy hiểm (SQL injection, DROP TABLE) và ngoài phạm vi | ❌ Rule-based |
| 2 | **Instruction Match** | Tìm quy tắc nghiệp vụ cần áp dụng (VD: "luôn lọc theo năm hiện tại") | ❌ Pattern match |

### 🟡 Giai đoạn 2: Phân tích ý định (Bước 3-4)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 3 | **Intent Classifier** | Xác định loại câu hỏi: truy vấn dữ liệu / hỏi về schema / trò chuyện | ✅ LLM |
| 4 | **Sub-Intent Detect** | Chi tiết hơn: RANKING / AGGREGATION / COMPARISON... | ❌ Keyword |

### 🟢 Giai đoạn 3: Tìm kiếm & liên kết schema (Bước 5-8)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 5 | **Schema Retrieval** | Dùng vector search tìm bảng/cột liên quan trong ChromaDB | ❌ Vector DB |
| 6 | **Schema Linking** | LLM xác nhận: "khách hàng" = bảng DimCustomer, cột FirstName | ✅ LLM |
| 7 | **Column Pruning** | Loại bỏ cột dư, giảm kích thước context | ✅ LLM |
| 8 | **Context Builder** | Ghép tất cả thành prompt hoàn chỉnh (DDL + relationships) | ❌ Template |

### 🔵 Giai đoạn 4: Bổ sung kiến thức (Bước 9-11)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 9 | **Glossary Inject** | Tra cứu thuật ngữ: "doanh thu" → `SUM(SalesAmount)` | ❌ YAML lookup |
| 10 | **Memory Lookup** | Tìm query tương tự đã thành công trước đó | ❌ Vector search |
| 11 | **CoT Reasoning** | Lập kế hoạch SQL: step-by-step suy luận trước khi viết | ✅ LLM |

### 🟣 Giai đoạn 5: Sinh & bảo vệ SQL (Bước 12-14)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 12 | **SQL Generation** | Sinh câu SQL từ toàn bộ context | ✅ LLM |
| 13 | **SQL Correction** | Chạy thử SQL, nếu lỗi → sửa tự động (tối đa 3 lần) | ✅ LLM |
| 13.5 | **Guardian** | Kiểm tra bảo mật: chống injection, read-only, masking | ❌ Rule-based |
| 14 | **Memory Save** | Lưu kết quả thành công vào bộ nhớ | ❌ File I/O |

### Tổng kết Pipeline

- **Tổng: 14 bước** (5 bước dùng LLM, 9 bước rule-based)
- **LLM calls mỗi query**: 4-6 lần
- **Thời gian trung bình**: 8-15 giây

---

## 5. Chart Generation

Sau khi có kết quả SQL, hệ thống dùng LLM để sinh biểu đồ:

```
Kết quả SQL → LLM phân tích → Chọn loại chart → Sinh Vega-Lite JSON → Render SVG
```

| Loại biểu đồ | Khi nào dùng | Ví dụ |
|--------------|-------------|-------|
| 📊 Bar | So sánh categories | Doanh thu theo sản phẩm |
| 📊 Grouped Bar | Sub-categories | Doanh thu theo sản phẩm + vùng |
| 📊 Stacked Bar | Composition | Tỷ lệ sản phẩm trong doanh thu |
| 📈 Line | Trend thời gian | Doanh thu theo tháng |
| 📈 Multi-line | Nhiều metrics | Doanh thu vs Chi phí |
| 📈 Area | Volume thời gian | Tổng đơn hàng tích lũy |
| 🥧 Pie | Tỉ lệ phần trăm | Cơ cấu khách hàng |

---

## 6. Kiến trúc kỹ thuật

### Component

| Thành phần | Công nghệ | Vai trò |
|-----------|-----------|---------|
| **Frontend** | Next.js 16, React 19, Ant Design | Giao diện chat, biểu đồ, ERD |
| **Backend** | Python, FastAPI | API server, pipeline engine |
| **LLM** | OpenAI GPT-4o | Sinh SQL, phân tích ý định |
| **Vector DB** | ChromaDB | Tìm kiếm bảng/cột tương tự |
| **Embeddings** | HuggingFace MiniLM | Chuyển text thành vector |
| **Database** | SQL Server | Nguồn dữ liệu thực |
| **Deploy** | Docker Compose | Đóng gói & triển khai |

### Sơ đồ kết nối

```
     ┌─────────────────────────────────────────────────────────┐
     │                    askDataAI                         │
     │                                                         │
     │  ┌─────────┐         ┌──────────────────────────────┐  │
     │  │ Next.js │  HTTP   │         FastAPI               │  │
     │  │   UI    │────────▶│                               │  │
     │  │         │         │  ┌──────────────────────────┐ │  │
     │  │ • Chat  │         │  │    14-Stage Pipeline     │ │  │
     │  │ • Chart │         │  │                          │ │  │
     │  │ • ERD   │         │  │ PreFilter → Intent →     │ │  │
     │  │ • Debug │         │  │ Schema → Prune → CoT →   │ │  │
     │  └─────────┘         │  │ Generate → Correct →     │ │  │
     │                      │  │ Guard → Save             │ │  │
     │                      │  └─────┬────────┬───────────┘ │  │
     │                      │        │        │             │  │
     │                      └────────┼────────┼─────────────┘  │
     │                               │        │                │
     │  ┌────────────┐     ┌────────▼──┐  ┌──▼──────────┐    │
     │  │  ChromaDB  │     │   LLM     │  │ SQL Server  │    │
     │  │  (Vectors) │     │  (GPT-4o) │  │  (Database) │    │
     │  └────────────┘     └───────────┘  └─────────────┘    │
     └─────────────────────────────────────────────────────────┘
```

---

## 7. Tính năng sắp tới

### 🔮 AI Auto-Description

**Hiện tại:** Khi kết nối database mới, người dùng phải mô tả thủ công từng bảng/cột → tốn rất nhiều thời gian (database 50+ bảng × 10 cột = 500+ descriptions).

**Giải pháp:** AI tự sinh descriptions dựa trên:
1. Tên bảng/cột (DimCustomer.FirstName → "Tên khách hàng")
2. Kiểu dữ liệu (INT, VARCHAR, DATE...)
3. Dữ liệu mẫu (scan vài dòng đầu)
4. Vài description mẫu do người dùng cung cấp (few-shot learning)

**Kết quả kỳ vọng:** Giảm thời gian setup từ **vài giờ** → **vài phút**.

---

## 8. Gợi ý slide

Dưới đây là gợi ý cấu trúc slide thuyết trình:

### Slide 1: Trang bìa
- Tên: askDataAI
- Subtitle: AI-powered Text-to-SQL Platform
- Team: KhoAI — DUT Startup

### Slide 2: Vấn đề
- Thống kê: bao nhiêu % nhân viên không biết SQL
- Pain point: phụ thuộc IT, mất thời gian, thiếu kịp thời

### Slide 3: Giải pháp
- Chat bằng tiếng Việt → nhận SQL + kết quả + biểu đồ
- Screenshot demo (chat UI)

### Slide 4: Demo Flow
- Sơ đồ: Câu hỏi → AI → SQL → Kết quả → Chart
- 3 ví dụ thực tế

### Slide 5: Pipeline (High-Level)
- 5 giai đoạn chính (dùng biểu đồ flow)
- Highlight: 14 bước, 4-6 LLM calls, 10-15 giây

### Slide 6: Pipeline (Chi tiết)
- Bảng 14 bước với icon (xem bảng ở mục 4)
- Highlight các bước dùng AI vs rule-based

### Slide 7: Chart Generation
- Trước/sau: bảng số → biểu đồ đẹp
- 7 loại chart

### Slide 8: Kiến trúc
- Sơ đồ tech stack (xem mục 6)

### Slide 9: Tính năng sắp tới
- AI Auto-Description
- Ví dụ: từ vài seed → sinh 500 descriptions

### Slide 10: Tổng kết & Q&A
- Tóm tắt value proposition
- Link demo / GitHub

---

*Tài liệu được tạo: 31/03/2026 — MiniWrenAI Team*
