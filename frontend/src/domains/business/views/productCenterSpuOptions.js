import { reactive } from "vue";

/**
 * SPU 值域 —— 前端只**消费**，不定义口径。
 *
 * 事故背景（2026-11-12）
 * ---------------------
 * 工具栏「所属 SPU」筛选器与新增 SKU 行的选款框，候选集原本直接绑定
 * 「SPU 管理」tab 的**分页表格数据**（`/api/spus` 默认 page=1、page_size=20）。
 * 而 `dim_spu` 实测 286 条 ⇒ 第 36 个 SPU（`XH-FASHION-001`）永远不在候选集里：
 * 运营输入后看到「无匹配数据」，回车不生效，筛选根本没发生。
 *
 * ⇒ 根因不是「翻页」，是**用实体列表当枚举值域**。
 * ⇒ 现在值域由后端按业务口径单独给出（`/api/spus/options` 与
 *    `/api/spus/assignable-options`），前端不再从任何表格里顺带拿数据。
 *
 * 两个口径的语义**不同**，不可混用：
 *   * browse —— 「在售的款有哪些」：用于**筛选**（查东西，敲什么都能查）；
 *   * assignable —— 「还能挂货的款有哪些」：用于**赋值**（外键，必须存在）。
 */

/**
 * 把后端返回的 SPU 行转成下拉选项。
 *
 * ⚠️ `label` 必须**等于** `value`：
 * Element Plus 的 `allow-create` 用 `option.currentLabel === inputValue`
 * 判断「这个值是否已存在」⇒ label 带名称的话，运营输入一个**已存在**的编码时
 * 会被误判为「不存在」，多弹一个「可创建」项。
 * 名称改用 slot 渲染（看得见，但不参与匹配判定）。
 *
 * @param {Array<{spu: string, spu_name?: string}>} rows 后端返回的行
 * @returns {Array<{value: string, label: string, name: string}>}
 */
export function buildSpuOptions(rows) {
  return (rows || []).map((row) => ({
    value: row.spu,
    label: row.spu,
    name: row.spu_name || "",
  }));
}

/**
 * 造一个远程搜索的 SPU 值域。
 *
 * ⚠️ 返回的**必须是 reactive 对象**，且 `options` / `loading` 是**普通值**。
 * 原因（2026-11-13 事故）：Vue 模板**只自动拆包「最外层」的 ref** ——
 * 若把 ref 藏在一个**普通对象**里（`{ options: ref([]) }`），模板拿到的
 * 是 **ref 本身**而不是名单：
 *   * `:loading="spu.loading"` 拿到的是 ref 对象（**恒为真**）
 *     ⇒ Element Plus 的规则 `选项列表 vShow = options.size > 0 && !loading`
 *     ⇒ 选项列表**永不渲染** ⇒ 下拉框是空的；
 *   * `v-for="item in spu.options"` 迭代的是 ref 的 5 个内部属性
 *     （`dep` / `__v_isRef` / `__v_isShallow` / `_rawValue` / `_value`）
 *     ⇒ 渲染出 5 个 value=undefined 的**空白项** ⇒ 一个款也选不中
 *     ⇒ 筛选条件永远是空 ⇒ 请求**从不带 `spu=`** ⇒ 表格不按款筛选。
 * ⇒ 完整分析见 `docs/superpowers/plans/2026-11-13-product-center-sku-spu-ui-defect-fix.md`；
 *   守护用例见 `frontend/tests/productCenterSpuOptionsRender.test.mjs`。
 *
 * @param {(params: {keyword: string, limit: number}) => Promise<{data?: Array}>} loadOptions
 *        值域查询函数（一般直接传 api 的方法）。
 * @param {{pageSize?: number, debounceMs?: number}} [options]
 */
export function createSpuSearch(loadOptions, { pageSize = 50, debounceMs = 300 } = {}) {
  let timer = null;

  // ⚠️ 状态直接挂在 reactive 对象上 ⇒ 模板与脚本拿到的都是**普通值**。
  //
  // ⚠️⚠️ 这个局部对象**不能叫 `api`**（2026-11-13 实测踩坑）：
  //   前端 API 契约门禁 ``scripts/validate_frontend_api_methods.py`` 用正则
  //   ``(?:this\.)?api\.(\w+)\s*\(`` 扫描 ``frontend/src``（不含 api 封装层），
  //   把**任何** ``api.xxx(...)`` 都当成后端接口调用来校验 ⇒
  //   局部对象一旦叫 `api`，它的 ``api.search(...)`` 就会被判成
  //   「调用了不存在的后端方法 search」⇒ **发版流水线红**。
  //   ⇒ 局部状态容器统一叫 `valueDomain`。
  const valueDomain = reactive({
    /** @type {Array<{value: string, label: string, name: string}>} */
    options: [],
    loading: false,

    async search(query = "") {
      valueDomain.loading = true;
      try {
        const res = await loadOptions({ keyword: query, limit: pageSize });
        valueDomain.options = buildSpuOptions(res && res.data);
      } catch {
        // 失败时**清空**候选：留着上一次的候选会让运营以为「这些款都搜不到」，
        // 而真正的原因是查询挂了。
        valueDomain.options = [];
      } finally {
        valueDomain.loading = false;
      }
    },

    remoteMethod(query) {
      // ⚠️ el-select 2.11.5 没有 debounce prop ⇒ remote-method 每次击键都会触发
      //    ⇒ 自己防抖，否则一次输入会打十几次后端。
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        void valueDomain.search(query);
      }, debounceMs);
    },
  });

  return valueDomain;
}
