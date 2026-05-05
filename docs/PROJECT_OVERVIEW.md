# 📖 askDataAI — TỔNG QUAN DỰ ÁN & PIPELINE
### Tài liệu dành cho thiết kế slide thuyết trình

---

## MỤC LỤC

1. [Dự án là gì?](#1-dự-án-là-gì)
2. [Vấn đề giải quyết](#2-vấn-đề-giải-quyết)
3. [Demo Flow](#3-demo-flow)
4. [Pipeline chi tiết (16 stages)](#4-pipeline-chi-tiết)
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

Pipeline xử lý gồm **16 bước**, chia thành 6 giai đoạn chính (Sprint 2-5 cập nhật):

### 🟤 Giai đoạn 0: Bảo mật & Ngữ cảnh (Bước 0-0.7)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 0 | **PI Guardrail** | Phát hiện prompt injection bằng local model offline | ❌ Local model |
| 0.5 | **Conversation Context** | mem0 inject context multi-turn | ❌ mem0 |
| 0.7 | **Question Translator** | Dịch VI → EN nội bộ trước khi vào pipeline | ✅ LLM |


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
| 5 | **Schema Retrieval** | Vector search ChromaDB + FK 1-hop. Bidirectional mode (Sprint 4): augment + table-first + column-first | ❌ hoặc ✅¹ |
| 6 | **Schema Linking** | LLM xác nhận: "khách hàng" = bảng DimCustomer, cột FirstName | ✅ LLM |
| 7 | **Column Pruning** | Loại bỏ cột dư, giảm kích thước context | ✅ LLM |
| 8 | **Context Builder** | DDL hoặc M-Schema (Sprint 2)² format | ❌ Template |

### 🔵 Giai đoạn 4: Bổ sung kiến thức (Bước 9-11)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 9 | **Glossary Inject** | Tra cứu thuật ngữ: "doanh thu" → `SUM(SalesAmount)` | ❌ YAML lookup |
| 10 | **Memory Lookup** | Tìm query tương tự đã thành công trước đó | ❌ Vector search |
| 11 | **CoT Reasoning** | Lập kế hoạch SQL: step-by-step suy luận trước khi viết | ✅ LLM |

### 🟣 Giai đoạn 5: Sinh & bảo vệ SQL (Bước 12-14)

| Bước | Tên | Làm gì? | Dùng AI? |
|------|-----|---------|----------|
| 12 | **SQL Generation** | Sinh N candidates + execution-based voting (skip nếu voting OFF) | ✅ LLM |
| 13 | **SQL Correction** | Chạy SQL, retry max 2-3 lần. 2 strategies: execution_only / taxonomy_guided³ | ✅ LLM |
| 13.5 | **Guardian** | Kiểm tra bảo mật: chống injection, read-only, masking | ❌ Rule-based |
| 14 | **Memory Save** | Lưu kết quả thành công vào bộ nhớ | ❌ File I/O |

¹ Bidirectional retrieval — `ENABLE_BIDIRECTIONAL_RETRIEVAL=true`. Cần re-deploy ChromaDB để tạo `column_descriptions` collection.
² M-Schema — `ENABLE_MSCHEMA=true`. Format key-value gọn hơn DDL ~30% tokens, đính kèm examples + ranges + inline FK.
³ Taxonomy correction — `CORRECTION_STRATEGY=taxonomy_guided`. Chia retry thành Plan + Fix.

### Tổng kết Pipeline

- **Tổng: 16 bước** (8 bước dùng LLM, 8 bước rule-based)
- **LLM calls mỗi query**: 5-9 lần (typical), tối đa 14 (full features)
- **Thời gian trung bình**: 15-25 giây
- **Benchmark hiện tại**: EX 48% trên 100 mẫu Vietnamese (Sprint 5.6)

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
| **LLM** | OpenAI GPT-4o-mini (default) | Sinh SQL, phân tích ý định |
| **Vector DB** | ChromaDB embedded | Tìm kiếm bảng/cột tương tự |
| **Embeddings** | OpenAI text-embedding-3-small | Chuyển text thành vector |
| **PI Guard** | Local Hugging Face model (offline) | Phát hiện prompt injection |
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

## 7. Sprint history & cải tiến SOTA

| Sprint | Nội dung | Toggle |
|---|---|---|
| 1 | Hand-craft 100-sample benchmark Vietnamese, canonical_hash + LLM judge | — |
| 2 | M-Schema format (XiYan-SQL) — examples + ranges + inline FK | `ENABLE_MSCHEMA` |
| 3 | YAML enrichment: Claude rewrite configs/models.yaml với data sampled từ DB | — |
| 4 | Bidirectional retrieval (XiYan): QuestionAugmenter + column_descriptions | `ENABLE_BIDIRECTIONAL_RETRIEVAL` |
| 5 | Taxonomy-guided correction (SQL-of-Thought): 9 categories × 25 sub-cat | `CORRECTION_STRATEGY` |
| 5.6 | Bug fixes: LIMIT 100 cutoff, taxonomy retry cap, toggle binding | `EXEC_ROW_LIMIT` |

**Benchmark progression** (100 mẫu AdventureWorks DW):
- Baseline: EX 41% (easy 43.3%, medium 55%, hard 20%)
- Sprint 5.6: **EX 48%** (easy 63.3% +20%, medium 60% +5%, hard 16.7% 0%)
- Latency p50: 23s, cost ~$0.025/run

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
