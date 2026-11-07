import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(process.cwd())
const drawerPath = resolve(
  projectRoot,
  'src/components/dataSync/VariantCreateWorkbenchDrawer.vue'
)
const viewPath = resolve(projectRoot, 'src/domains/data_platform/views/DataSyncTemplates.vue')

assert.equal(existsSync(drawerPath), true, 'VariantCreateWorkbenchDrawer.vue should exist')
assert.equal(existsSync(viewPath), true, 'DataSyncTemplates.vue should exist')

const drawerText = readFileSync(drawerPath, 'utf8')
const viewText = readFileSync(viewPath, 'utf8')

// ---------------------------------------------------------------------------
// 批次 G(G-3): 变体抽屉按**业务维度**建
// ---------------------------------------------------------------------------
assert.match(
  drawerText,
  /业务形态/,
  'variant create drawer should surface the business form of the variant'
)
assert.match(
  drawerText,
  /recommended_business_form/,
  'variant create drawer should read the business form from the create context'
)
assert.match(
  drawerText,
  /recommended_variant_kind/,
  'variant create drawer should read the recommended business-form identifier'
)
assert.match(
  drawerText,
  /existing_variants/,
  'variant create drawer should list the business forms of existing variants'
)
assert.match(
  drawerText,
  /el-descriptions/,
  'variant create drawer should render the business-form dimensions'
)
assert.match(
  drawerText,
  /不再按文件名切分|文件名/,
  'variant create drawer should state that the filename no longer drives variants'
)

// 业务维度: 平台 / 数据域 / 子域 / 粒度 / 表头行 / 列数 / 工作表名
for (const label of ['平台', '数据域', '子域', '粒度', '表头行', '列数', '工作表名模式']) {
  assert.ok(
    drawerText.includes(`label="${label}"`),
    `business form should display the ${label} dimension`
  )
}

// ---------------------------------------------------------------------------
// 旧口径(按文件名分隔符切分)不得再出现
// ---------------------------------------------------------------------------
assert.doesNotMatch(
  drawerText,
  /slash|dash/i,
  'variant create drawer should not carry the retired filename-separator convention'
)

// ---------------------------------------------------------------------------
// 保存时模板名用形态标识, 不用文件名关键词
// ---------------------------------------------------------------------------
assert.match(
  viewText,
  /recommended_variant_kind/,
  'variant save flow should build the template name from the business-form identifier'
)
assert.match(
  viewText,
  /variantKind/,
  'variant save flow should resolve the business-form identifier before naming the template'
)
