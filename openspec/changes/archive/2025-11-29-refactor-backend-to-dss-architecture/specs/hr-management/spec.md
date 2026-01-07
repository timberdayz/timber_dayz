# HR Management Specification

## ADDED Requirements

### Requirement: Employee Management Tables (Chinese Column Names)
The database SHALL store employee management data in tables with Chinese column names.

#### Scenario: Employee profile storage
- **WHEN** employee profile is created
- **THEN** the system SHALL store in `employees` table with Chinese column names:
  - `"员工编号"` (employee_id, primary key)
  - `"姓名"` (name)
  - `"部门"` (department)
  - `"职位"` (position)
  - `"入职日期"` (hire_date)
  - `"状态"` (status: active/inactive)
  - `"联系方式"` (contact_info, JSONB)
- **AND** PostgreSQL SHALL support Chinese column names (using double quotes)
- **AND** Metabase SHALL display Chinese column names directly

#### Scenario: Employee target storage
- **WHEN** employee targets are configured
- **THEN** the system SHALL store in `employee_targets` table with Chinese column names:
  - `"员工编号"` (employee_id, foreign key to employees)
  - `"年月"` (year_month, format: '2025-01')
  - `"目标类型"` (target_type: sales/orders/customers)
  - `"目标值"` (target_value, numeric)
  - `"单位"` (unit: amount/count/percentage)
- **AND** SHALL support multiple target types per employee per month

#### Scenario: Attendance record storage
- **WHEN** attendance record is created
- **THEN** the system SHALL store in `attendance_records` table with Chinese column names:
  - `"员工编号"` (employee_id, foreign key to employees)
  - `"考勤日期"` (attendance_date, date)
  - `"上班时间"` (check_in_time, timestamp)
  - `"下班时间"` (check_out_time, timestamp)
  - `"工作时长"` (work_hours, numeric)
  - `"考勤状态"` (status: normal/late/early_leave/absent)
- **AND** SHALL support multiple records per employee per day (if needed)

**Rationale**: Chinese column names are user-friendly for Chinese users, and both PostgreSQL and Metabase support them. Employee management data is A-class data (user-configured), so it uses Chinese column names for consistency.

### Requirement: Employee Performance Calculation (Metabase Scheduled Tasks)
The system SHALL calculate employee performance metrics using Metabase scheduled tasks and store results in C-class data tables.

#### Scenario: Employee performance calculation
- **WHEN** Metabase scheduled task runs (every 20 minutes)
- **THEN** the system SHALL:
  - Query `fact_raw_data_orders_*` tables, join with `employees` table
  - Calculate per employee metrics:
    - `"实际销售额"` (actual_sales_amount, sum of sales)
    - `"实际订单数"` (actual_order_count, count of orders)
    - `"达成率"` (achievement_rate, actual / target * 100)
    - `"排名"` (ranking, within department)
  - Store results in `employee_performance` table with Chinese column names:
    - `"员工编号"`, `"年月"`, `"实际销售额"`, `"实际订单数"`, `"达成率"`, `"排名"`
- **AND** SHALL update existing records or insert new records
- **AND** SHALL handle missing targets gracefully (set achievement_rate to NULL)

#### Scenario: Employee commission calculation
- **WHEN** Metabase scheduled task runs (every 20 minutes)
- **THEN** the system SHALL:
  - Query `employee_performance` table and commission rules
  - Calculate commission based on sales amount and commission rate
  - Store results in `employee_commissions` table with Chinese column names:
    - `"员工编号"`, `"年月"`, `"销售额"`, `"提成率"`, `"提成金额"`
- **AND** SHALL support different commission rates per employee or department

#### Scenario: Shop commission calculation
- **WHEN** Metabase scheduled task runs (every 20 minutes)
- **THEN** the system SHALL:
  - Query `fact_raw_data_orders_*` tables, aggregate by shop
  - Calculate shop-level commission based on shop sales
  - Store results in `shop_commissions` table with Chinese column names:
    - `"店铺ID"`, `"年月"`, `"销售额"`, `"提成率"`, `"提成金额"`
- **AND** SHALL support different commission rates per shop

**Rationale**: Performance and commission calculations are C-class data (system-calculated), updated by Metabase scheduled tasks every 20 minutes. This ensures data freshness while avoiding real-time calculation overhead.

### Requirement: HR Management API (Future Implementation)
The system SHALL provide RESTful API endpoints for HR management operations.

#### Scenario: Employee CRUD operations
- **WHEN** frontend requests employee list
- **THEN** API SHALL provide:
  - `GET /api/hr/employees` - List employees (with pagination, filtering)
  - `POST /api/hr/employees` - Create employee
  - `PUT /api/hr/employees/{id}` - Update employee
  - `DELETE /api/hr/employees/{id}` - Delete employee (soft delete)
- **AND** SHALL validate Chinese column names in request/response
- **AND** SHALL return data with Chinese column names

#### Scenario: Employee target CRUD operations
- **WHEN** frontend requests employee targets
- **THEN** API SHALL provide:
  - `GET /api/hr/employee-targets` - List targets (filter by employee_id, year_month)
  - `POST /api/hr/employee-targets` - Create target
  - `PUT /api/hr/employee-targets/{id}` - Update target
  - `DELETE /api/hr/employee-targets/{id}` - Delete target
- **AND** SHALL support batch operations (create/update multiple targets)

#### Scenario: Attendance record CRUD operations
- **WHEN** frontend requests attendance records
- **THEN** API SHALL provide:
  - `GET /api/hr/attendance` - List records (filter by employee_id, date_range)
  - `POST /api/hr/attendance` - Create record
  - `PUT /api/hr/attendance/{id}` - Update record
  - `DELETE /api/hr/attendance/{id}` - Delete record
- **AND** SHALL validate work hours calculation (check_out_time - check_in_time)

#### Scenario: Performance query operations
- **WHEN** frontend requests employee performance
- **THEN** API SHALL provide:
  - `GET /api/hr/performance` - Query performance (from `employee_performance` table)
  - `GET /api/hr/commissions` - Query commissions (from `employee_commissions` and `shop_commissions` tables)
- **AND** SHALL support filtering by employee_id, shop_id, year_month
- **AND** SHALL return data with Chinese column names

**Note**: HR Management API is planned for Phase 3 implementation. Phase 0 focuses on table structure creation, and Phase 3 will implement API endpoints.

### Requirement: HR Management Frontend Interface (Future Implementation)
The system SHALL provide Vue.js frontend interfaces for HR management operations.

#### Scenario: Employee management interface
- **WHEN** user navigates to employee management page
- **THEN** frontend SHALL display:
  - Employee list table (with Chinese column names)
  - Add/Edit/Delete buttons
  - Search and filter functionality
  - Pagination
- **AND** SHALL use Element Plus Table component with inline editing support

#### Scenario: Commission management interface
- **WHEN** user navigates to commission management page
- **THEN** frontend SHALL display:
  - Employee commissions table (from `employee_commissions` table)
  - Shop commissions table (from `shop_commissions` table)
  - Performance metrics (from `employee_performance` table)
  - Filter by employee, shop, month
  - Export to Excel functionality
- **AND** SHALL display data with Chinese column names
- **AND** SHALL show last update timestamp (from Metabase scheduled task)

**Note**: HR Management frontend interfaces are planned for Phase 3 implementation. Phase 0 focuses on table structure creation, and Phase 3 will implement frontend components.

