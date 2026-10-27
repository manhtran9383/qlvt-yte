# QLVT Y tế

## Professional Management Software for Medical Inventory

QLVT Y tế is a comprehensive medical inventory management software designed for hospitals, clinics, and pharmacies. It replaces traditional Excel-based management with a modern desktop application featuring role-based access control and full offline capabilities.

### Key Features

| Feature | Description |
|---------|-------------|
| **POS Sales** | Create shipment invoices with auto-pricing from contracts |
| **Inventory Management** | Real-time stock tracking with expiration alerts |
| **Customer Management** | Manage hospitals, clinics, and pharmacies |
| **Contract Tracking** | Monitor delivery progress per contract |
| **Cash/Carry (Ký Gửi)** | Send goods to hospitals, sell from consignment stock |
| **Proforma Invoices** | Issue invoices before delivery, reconcile after |
| **Customer History** | Query transactions by customer + time period |
| **Reporting** | Monthly/quarterly revenue, part analysis, inventory charts |
| **Delivery Reports** | PDF invoices with digital signatures (Desktop) |
| **Authentication** | 5 roles: admin, kinhdoanh, ketoan, kho, nhanvien |

### System Requirements

- **OS:** Windows 10/11 (64-bit)
- **RAM:** ≥ 2 GB
- **Storage:** ≥ 100 MB free
- **Python:** 3.11+ (for source runtime)
- **Offline:** No internet required, SQLite embedded

### Quick Start

#### From Source
```bash
cd src
pip install customtkinter reportlab bcrypt pyinstaller
python app_desktop.py
```

#### Build to .exe
```bash
python -m PyInstaller QLVT-YTe.spec --clean
# Output: dist/QLVT-YTe.exe
```

### Architecture

QLVT Y tế uses a **dual-interface, single-business-logic** approach:

- **Desktop** (`src/app_desktop.py`): CustomTkinter GUI for local network management
- **Web** (planned): Django/FastAPI + frontend for remote access
- **CLI** (`src/import_excel.py`): Terminal-based Excel import
- **Core** (`src/qlvt_core.py`): Shared business logic used by all interfaces

All interfaces connect to the same SQLite database with WAL mode for concurrent access.

### License

This project is licensed under the **MIT License**.

- GitHub: `manhtran9383/qlvt-yte`
- Email: `manhtran9383@gmail.com`

---

*Version 3.0 — Complete bug fix release (October 2026)*
*All 15 P0/P1 bugs resolved: to_float accuracy, PDF signatures, DB path stability, theme packing*
