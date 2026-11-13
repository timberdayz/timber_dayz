import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createSSRApp, h } from "vue";
import { renderToString } from "vue/server-renderer";

import {
  SPU_OPTION_EMPTY_TEXT,
  buildSkuEmptyText,
} from "../src/domains/business/views/productCenterSpuOptions.js";

/**
 * 空结果文案的守护（批次 B2）。
 *
 * 为什么值得单独一个文件
 * ----------------------
 * 「没有结果」是最容易骗人的界面状态：后端返回空数组是**正确**的，
 * 但 Element Plus 的默认文案（「暂无数据」/「无数据」）不告诉运营
 * **为什么**空、下一步该做什么 ⇒ 运营要么以为系统坏了，要么反复重试。
 *
 * 真实案例（2026-11-13 实测，生产）：
 *   `XH-FASHION-005` 当前挂货 **0** 条 ⇒ 运营选中它后表格空白，
 *   看见「暂无数据」根本想不到"是这个款还没有货"。
 *
 * ⇒ 本文件锁两件事：
 *   1. 文案**本身**说清原因 + 下一步（运行时断言）；
 *   2. 组件**真的**把这段文案接到了表格与两个下拉上（接线断言）。
 */

const root = resolve(import.meta.dirname, "..");
const source = readFileSync(
  resolve(root, "src/domains/business/views/ProductCenter.vue"),
  "utf8",
);

/** 取某个锚点附近的源码片段（用于"这段文案有没有接在正确的控件上"）。 */
function blockAround(needle, before = 260, after = 320) {
  const idx = source.indexOf(needle);
  assert.ok(idx >= 0, `源码里找不到锚点：${needle}`);
  return source.slice(Math.max(0, idx - before), idx + after);
}

// ---------------------------------------------------------------------------
// 文案本身
// ---------------------------------------------------------------------------

test("没按款筛时，表格空态沿用默认的「暂无数据」", () => {
  assert.equal(buildSkuEmptyText(""), "暂无数据");
  assert.equal(buildSkuEmptyText(null), "暂无数据");
  assert.equal(buildSkuEmptyText(undefined), "暂无数据");
  assert.equal(buildSkuEmptyText("   "), "暂无数据");
});

test("按款筛时，空态点名是**哪个款**没有挂货", () => {
  const text = buildSkuEmptyText("XH-FASHION-005");
  assert.match(text, /XH-FASHION-005/, "必须点名那个款");
  assert.match(text, /没有挂货/, "必须说清原因");
  assert.notEqual(text, "暂无数据", "不能还是笼统的「暂无数据」");
});

test("空态文案能被真的渲染出来（运行时断言，不是读源码）", async () => {
  const app = createSSRApp({
    setup() {
      return { text: buildSkuEmptyText("XH-TOYS-MYTK") };
    },
    render() {
      return h("div", { class: "el-table__empty-text" }, this.text);
    },
  });

  const html = await renderToString(app);
  assert.match(html, /XH-TOYS-MYTK/);
  assert.match(html, /没有挂货/);
});

test("两个口径的下拉空态文案各自说清下一步，且互不相同", () => {
  const { browse, assignable } = SPU_OPTION_EMPTY_TEXT;

  assert.ok(browse && assignable, "两套文案都必须存在");
  assert.notEqual(browse, assignable, "浏览口径与可绑定口径的下一步不一样，文案不能一样");
  assert.match(browse, /关键词/, "浏览口径（筛选）要提示换个关键词");
  assert.match(assignable, /新建款/, "可绑定口径（赋值）要提示先去建款");
  for (const text of [browse, assignable]) {
    assert.notEqual(text, "无数据");
    assert.notEqual(text, "暂无数据");
  }
});

// ---------------------------------------------------------------------------
// 接线：文案必须挂在正确的控件上
// ---------------------------------------------------------------------------

test("SKU 表格接上了按款判定的空态文案", () => {
  const skuTableIdx = source.indexOf(':data="skus"');
  assert.ok(skuTableIdx >= 0, "找不到 SKU 表格");
  const tableStart = source.lastIndexOf("<el-table", skuTableIdx);
  const tableBlock = source.slice(tableStart, skuTableIdx + 400);

  assert.match(
    tableBlock,
    /:empty-text="skuEmptyText"/,
    "SKU 表格必须用动态空态文案（不是 Element Plus 的默认「暂无数据」）",
  );
});

test("skuEmptyText 由筛选条件算出", () => {
  assert.match(
    source,
    /const skuEmptyText = computed\(\(\) => buildSkuEmptyText\(skuSpuFilter\.value\)\)/,
    "空态文案必须跟着「所属 SPU」筛选条件走",
  );
});

test("浏览口径下拉接的是 browse 文案，可绑定下拉接的是 assignable 文案", () => {
  const browseBlock = blockAround(':remote-method="spuBrowse.remoteMethod"');
  const assignableBlock = blockAround(':remote-method="spuAssignable.remoteMethod"');

  assert.match(browseBlock, /:no-data-text="SPU_OPTION_EMPTY_TEXT\.browse"/);
  assert.doesNotMatch(browseBlock, /SPU_OPTION_EMPTY_TEXT\.assignable/);

  assert.match(assignableBlock, /:no-data-text="SPU_OPTION_EMPTY_TEXT\.assignable"/);
  assert.doesNotMatch(assignableBlock, /SPU_OPTION_EMPTY_TEXT\.browse/);
});
