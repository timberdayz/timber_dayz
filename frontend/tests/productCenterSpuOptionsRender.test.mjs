import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { createSSRApp, h } from "vue";
import { renderToString } from "vue/server-renderer";

import { createSpuSearch } from "../src/domains/business/views/productCenterSpuOptions.js";

/**
 * SPU 值域的**运行时**守护。
 *
 * 为什么要有这个文件（2026-11-13 事故）
 * ------------------------------------
 * 兄弟文件 `productCenterSpuOptions.test.mjs` 断言的是**源码文本**
 * （"用了 remote / 用了 allow-create / 接对了端点"）⇒ 它**看不见**下面这类缺陷：
 *
 *   值域工厂返回的是 `{ options: ref([]), loading: ref(false) }` —— 普通对象里藏着 ref。
 *   Vue 模板**只自动拆包最外层的 ref** ⇒ 模板拿到的不是名单，而是 ref 本身：
 *     * `:loading="spu.loading"` ⇒ 恒为真 ⇒ Element Plus 的规则
 *       `选项列表 vShow = options.size > 0 && !loading` ⇒ **选项列表永不渲染**；
 *     * `v-for="item in spu.options"` ⇒ 迭代 ref 的 5 个内部属性 ⇒ **5 个空白项**；
 *     * ⇒ 一个款也选不中 ⇒ 筛选条件永远为空 ⇒ 请求**从不带 `spu=`**
 *       ⇒ 表格**永远不按款筛选**（运营看到"筛的是 A、列的是 B"）。
 *
 * ⇒ 后端、日志、数据全都正确，**只有界面是坏的** —— 所以必须有一道
 *   **真的渲染一次**的断言，不能只读源码。
 *
 * 完整分析：`docs/superpowers/plans/2026-11-13-product-center-sku-spu-ui-defect-fix.md`
 */

const root = resolve(import.meta.dirname, "..");
const source = readFileSync(
  resolve(root, "src/domains/business/views/ProductCenter.vue"),
  "utf8",
);
const factorySource = readFileSync(
  resolve(root, "src/domains/business/views/productCenterSpuOptions.js"),
  "utf8",
);

const FAKE_ROWS = [
  { spu: "XH-FASHION-005", spu_name: "Kuromi school bag trolley primary school" },
];

function makeSearch(rows = FAKE_ROWS) {
  return createSpuSearch(async () => ({ data: rows }));
}

// ---------------------------------------------------------------------------
// 病根本身：模板可见路径拿到的是「名单」，不是「装着名单的盒子」
// ---------------------------------------------------------------------------

test("模板可见路径拿到的是名单本身，不是装着名单的 ref 盒子", async () => {
  const spu = makeSearch();
  await spu.search("");

  // ⚠️ 这两条就是那三个症状的源头：
  //    options 若是 ref ⇒ v-for 迭代出空白项；loading 若是 ref ⇒ 恒为真。
  assert.ok(Array.isArray(spu.options), "options 必须是名单（数组），不是 ref 容器");
  assert.equal(
    typeof spu.loading,
    "boolean",
    "loading 必须是布尔值，不是恒为真的 ref 对象",
  );
  assert.equal(spu.options.length, 1);
  assert.equal(spu.options[0].value, "XH-FASHION-005");
  assert.equal(spu.options[0].label, "XH-FASHION-005");
  assert.equal(spu.options[0].name, "Kuromi school bag trolley primary school");
});

test("真渲染一次：款编码必须出现在渲染结果里，而不是空白项", async () => {
  const spu = makeSearch();
  await spu.search("");

  // 用 render function 而不是 template ⇒ 不依赖运行期模板编译器。
  const app = createSSRApp({
    setup() {
      return { spu };
    },
    render() {
      return h(
        "ul",
        this.spu.options.map((item) =>
          h("li", { key: item.value }, `${item.label}|${item.value}`),
        ),
      );
    },
  });

  const html = await renderToString(app);
  assert.match(html, /XH-FASHION-005/, "渲染结果里必须出现真实款编码");
  assert.doesNotMatch(html, /\[object Object\]/, "渲染出了对象而不是名单");
  assert.doesNotMatch(html, /\|\|/, "渲染出了 value 为空的空白项");
});

test("搜索失败时候选被清空（不留上一次的名单）且 loading 解除", async () => {
  const spu = createSpuSearch(async () => {
    throw new Error("boom");
  });
  await spu.search("X");

  assert.deepEqual(spu.options, []);
  assert.equal(spu.loading, false);
});

// ---------------------------------------------------------------------------
// 结构性门禁：别再写回「普通对象 + 嵌套 ref」
// ---------------------------------------------------------------------------

test("值域工厂必须用 reactive 包装状态，不许再 import ref", () => {
  assert.match(factorySource, /reactive\(/, "工厂必须用 reactive 包装状态");
  assert.doesNotMatch(
    factorySource,
    /import\s*\{[^}]*\bref\b[^}]*\}\s*from\s*"vue"/,
    "工厂不许再 import ref —— 藏在普通对象里的 ref 会被模板当成盒子",
  );
});

test("组件按新契约取值：不再对值域对象取 .value", () => {
  assert.doesNotMatch(source, /spuBrowse\.[a-zA-Z]+\.value/);
  assert.doesNotMatch(source, /spuAssignable\.[a-zA-Z]+\.value/);
});
