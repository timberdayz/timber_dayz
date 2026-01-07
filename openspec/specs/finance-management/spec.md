# 财务管理能力

## Requirements

### Requirement: CNY本位币
系统应使用CNY作为本位币，并为所有交易存储原始货币金额和CNY转换金额。

#### Scenario: 多货币交易存储
- **WHEN** 以外币（例如USD、SGD、BRL）发生交易
- **THEN** 系统在原始货币中存储amount_original，在CNY中存储amount_cny，以及汇率快照

#### Scenario: 交易时的货币转换
- **WHEN** 创建USD采购订单
- **THEN** 系统获取USD到CNY的汇率，转换金额，并在purchase_order表中存储USD和CNY金额

### Requirement: 统一流水账
系统应为所有财务交易（包括总账、库存和费用）维护统一的流水账分录。

#### Scenario: 流水账分录创建
- **WHEN** 发生财务交易（采购、销售、费用、库存变动）
- **THEN** 系统在fact_gl_journal中创建流水账分录，包含借方/贷方账户、金额和交易参考

#### Scenario: 多账户流水账分录
- **WHEN** 收到采购订单
- **THEN** 系统创建流水账分录，借记库存账户并贷记应付账款账户

### Requirement: 移动加权平均成本
系统应使用移动加权平均成本方法实时计算库存成本。

#### Scenario: 库存收货时的成本计算
- **WHEN** 货物收到入库
- **THEN** 系统重新计算加权平均成本：(旧成本 * 旧数量 + 新成本 * 新数量) / (旧数量 + 新数量)

#### Scenario: 销售时的成本更新
- **WHEN** 产品销售
- **THEN** 系统使用当前加权平均成本计算销售成本（COGS）并更新库存价值

### Requirement: 三单匹配
系统应自动匹配采购订单（PO）、收货单（GRN）和发票以进行对账。

#### Scenario: PO-GRN-发票匹配
- **WHEN** 收到采购订单的发票
- **THEN** 系统将发票行项目与相应的GRN和PO匹配，验证数量和金额是否匹配，并标记为已匹配

#### Scenario: 匹配差异处理
- **WHEN** 发票金额与PO金额不同
- **THEN** 系统标记差异，允许用户审核，并支持手动调整或批准

### Requirement: 费用分摊引擎
系统应支持多驱动的费用分摊到店铺、SKU和日期维度。

#### Scenario: 按店铺分摊费用
- **WHEN** 营销费用分摊到多个店铺
- **THEN** 系统根据分摊驱动（例如，销售量、收入份额）分配费用金额，并为每个店铺创建费用记录

#### Scenario: 按SKU分摊费用
- **WHEN** 运费分摊到订单项
- **THEN** 系统根据重量或体积将运费分摊到每个SKU，并为每个SKU创建费用记录

#### Scenario: 按日期分摊费用
- **WHEN** 分摊月度租金费用
- **THEN** 系统将费用分配到月份中的每一天，并创建每日费用记录

### Requirement: 应收账款管理
系统应跟踪应收账款（AR），在订单完成时自动创建，并提供逾期提醒。

#### Scenario: 订单时创建AR
- **WHEN** 订单状态变为已完成
- **THEN** 系统自动在fact_accounts_receivable中创建AR记录，包含订单参考、金额、到期日和状态

#### Scenario: AR付款记录
- **WHEN** 收到AR付款
- **THEN** 系统将AR状态更新为已付款，记录付款日期，并创建流水账分录，借记现金并贷记AR

#### Scenario: 逾期AR提醒
- **WHEN** AR到期日已过但未付款
- **THEN** 系统自动将AR标记为逾期并生成提醒通知

### Requirement: 应付账款管理
系统应跟踪应付账款（AP），在采购订单收货时自动创建。

#### Scenario: GRN时创建AP
- **WHEN** 通过GRN收到货物
- **THEN** 系统在fact_accounts_payable中创建AP记录，包含供应商参考、金额、到期日，并链接到PO和GRN

#### Scenario: AP付款记录
- **WHEN** 向供应商付款
- **THEN** 系统将AP状态更新为已付款，记录付款日期，并创建流水账分录，借记AP并贷记现金

### Requirement: 税务合规
系统应支持增值税、所得税和出口退税的计算和合规。

#### Scenario: 增值税计算
- **WHEN** 发生销售交易
- **THEN** 系统根据税率计算增值税金额，并在fact_tax_transactions中创建税务记录

#### Scenario: 出口退税
- **WHEN** 出口订单完成
- **THEN** 系统计算符合条件的退税金额并创建退税记录

### Requirement: 财务报表
系统应提供财务报表，包括损益表（P&L）、资产负债表和现金流量表。

#### Scenario: P&L报表生成
- **WHEN** 用户请求日期范围的P&L报表
- **THEN** 系统从流水账分录和物化视图汇总收入、COGS、费用，并计算净利润

#### Scenario: 资产负债表生成
- **WHEN** 用户请求截至日期的资产负债表
- **THEN** 系统从账户余额计算资产（现金、库存、AR）、负债（AP、贷款）和权益
