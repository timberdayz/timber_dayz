import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import {
  buildSpuOptions,
  createSpuSearch,
} from "../src/domains/business/views/productCenterSpuOptions.js";

const root = resolve(import.meta.dirname, "..");
const source = readFileSync(
  resolve(root, "src/domains/business/views/ProductCenter.vue"),
  "utf8",
);
const api = readFileSync(resolve(root, "src/api/productCenter.js"), "utf8");

// ---------------------------------------------------------------------------
// 值域模块本身的行为
// ---------------------------------------------------------------------------

test("值域选项的 label 必须等于 value —— 否则 allow-create 会误判「不存在」", () => {
  const options = buildSpuOptions([
    { spu: "XH-FASHION-001", spu_name: "Primary School bag" },
  ]);

  assert.equal(options.length, 1);
  assert.equal(options[0].value, "XH-FASHION-001");
  // ⚠️ Element Plus 的 showNewOption 用 `option.currentLabel === inputValue`
  //    判断「是否已存在」⇒ label 带名称会让输入已有编码时误判为不存在，
  //    多弹一个「可创建」项。名称改用 slot 渲染。
  assert.equal(options[0].label, "XH-FASHION-001");
  assert.equal(options[0].name, "Primary School bag");
});

test("值域选项对空数据与缺名称都安全", () => {
  assert.deepEqual(buildSpuOptions(null), []);
  assert.deepEqual(buildSpuOptions(undefined), []);
  assert.equal(buildSpuOptions([{ spu: "XH-1" }])[0].name, "");
});

test("值域搜索按关键词请求后端，并把结果转成选项", async () => {
  const calls = [];
  const search = createSpuSearch(async (params) => {
    calls.push(params);
    return { data: [{ spu: "XH-FASHION-001", spu_name: "Bag" }] };
  });

  await search.search("FASHION");

  assert.equal(calls.length, 1);
  assert.equal(calls[0].keyword, "FASHION");
  assert.ok(calls[0].limit > 0, "必须带 limit，避免一次拉回全部 SPU");
  assert.equal(search.options.length, 1);
  assert.equal(search.options[0].value, "XH-FASHION-001");
});

test("值域搜索失败时清空候选，不把上一次的结果留在框里", async () => {
  const search = createSpuSearch(async () => {
    throw new Error("boom");
  });

  await search.search("X");

  assert.deepEqual(search.options, []);
  assert.equal(search.loading, false);
});

test("值域搜索结束一定会解除 loading", async () => {
  const search = createSpuSearch(async () => ({ data: [] }));

  await search.search("X");

  assert.equal(search.loading, false);
});

// ---------------------------------------------------------------------------
// 接线：两处下拉不再依赖「SPU 管理」tab 的分页数据
// ---------------------------------------------------------------------------

test("两处选款框都不再绑定 SPU 管理 tab 的分页表格数据", () => {
  // ⚠️ 事故根因：`spus` 是 /api/spus 的**分页**结果（默认 page=1、page_size=20）
  //    ⇒ 第 36 个 SPU 永远不在候选集里，运营输入后只看到「无匹配数据」。
  assert.doesNotMatch(
    source,
    /v-for="spu in spus"/,
    "选款框还在用 SPU 管理 tab 的分页数据",
  );
});

test("工具栏「所属 SPU」是查询条件：可远程搜索、可直接输入编码生效", () => {
  const filter = source.slice(
    source.indexOf('v-model="skuSpuFilter"'),
    source.indexOf('v-model="skuQuery.status"'),
  );

  assert.match(filter, /\bremote\b/, "筛选器必须远程搜索，不能只过滤已加载的 20 条");
  assert.match(filter, /allow-create/, "筛选器必须允许直接输入编码回车生效");
  assert.match(filter, /remote-method/);
});

test("新增 SKU 行的选款框是外键：可远程搜索但不能凭空造值", () => {
  // ⚠️ `v-model="row.spu"` 在「SPU 管理」tab 里也出现过（SPU 编码输入框），
  //    所以不能用它定位 —— 用唯一的 remote-method 反查这一段 el-select。
  const anchor = source.indexOf("spuAssignable.remoteMethod");
  assert.notEqual(anchor, -1, "新增 SKU 行的选款框必须接可绑定口径的值域");
  const picker = source.slice(
    source.lastIndexOf("<el-select", anchor),
    source.indexOf("</el-select", anchor),
  );

  assert.match(picker, /\bremote\b/, "选款框必须远程搜索，否则选不到第 2 页之后的款");
  assert.doesNotMatch(
    picker,
    /allow-create/,
    "选款框是外键，不允许造出库里不存在的 SPU",
  );
});

test("两处下拉分别使用浏览口径与可绑定口径的值域端点", () => {
  assert.match(api, /listSpuOptions/);
  assert.match(api, /listSpuAssignableOptions/);
  assert.match(api, /\/spus\/options/);
  assert.match(api, /\/spus\/assignable-options/);
});
