import { ref } from "vue";

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
 * @param {(params: {keyword: string, limit: number}) => Promise<{data?: Array}>} loadOptions
 *        值域查询函数（一般直接传 api 的方法）。
 * @param {{pageSize?: number, debounceMs?: number}} [options]
 */
export function createSpuSearch(loadOptions, { pageSize = 50, debounceMs = 300 } = {}) {
  const options = ref([]);
  const loading = ref(false);
  let timer = null;

  async function search(query = "") {
    loading.value = true;
    try {
      const res = await loadOptions({ keyword: query, limit: pageSize });
      options.value = buildSpuOptions(res && res.data);
    } catch {
      // 失败时**清空**候选：留着上一次的候选会让运营以为「这些款都搜不到」，
      // 而真正的原因是查询挂了。
      options.value = [];
    } finally {
      loading.value = false;
    }
  }

  function remoteMethod(query) {
    // ⚠️ el-select 2.11.5 没有 debounce prop ⇒ remote-method 每次击键都会触发
    //    ⇒ 自己防抖，否则一次输入会打十几次后端。
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      void search(query);
    }, debounceMs);
  }

  return { options, loading, search, remoteMethod };
}
