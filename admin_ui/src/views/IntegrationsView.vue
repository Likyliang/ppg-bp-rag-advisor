<script setup lang="ts">
import { computed, inject, ref, type Ref } from "vue";
import { api, jsonBody } from "../api";
import FeedbackBanner from "../components/FeedbackBanner.vue";
import PageHeader from "../components/PageHeader.vue";
import StatusBadge from "../components/StatusBadge.vue";
import { usePolling } from "../composables/usePolling";

const user = inject<Ref<any>>("adminUser")!;
const rows = ref<any[]>([]);
const secrets = ref<Record<string, string>>({});
const results = ref<Record<string, any>>({});
const acting = ref("");
const message = ref("");
const channelMeta: Record<string, any> = {
  report_llm: { title: "用户报告 / 随访 LLM", description: "生成保守解释；无有效配置时回退到模板报告。", providers: ["mock", "deepseek", "anthropic", "claude", "openai_compatible"] },
  embedding: { title: "OpenAI Embedding", description: "仅构建官方 OpenAI 摘要或全文向量，不复用本地 BGE。", providers: ["openai"] },
  evaluation: { title: "离线评估 Judge", description: "只发送去标识化评测 fixture；V1 永不发送全文。", providers: ["openai_compatible"] },
  crossref: { title: "Crossref 元数据", description: "只查询公开书目信息，不需要 API Key。", providers: ["crossref"] },
};
const configuredCount = computed(() => rows.value.filter((row) => row.enabled && (row.channel === "crossref" || row.provider === "mock" || row.secret_configured)).length);

async function load() {
  const result = await api<any>("/api/v1/admin/integrations");
  rows.value = (result.integrations || []).map((row: any) => ({ ...row, settings: { ...(row.settings || {}) } }));
}

async function save(row: any) {
  acting.value = `save:${row.channel}`;
  message.value = "";
  try {
    await api(`/api/v1/admin/integrations/${row.channel}`, {
      method: "PUT",
      body: jsonBody({
        provider: row.provider,
        base_url: row.base_url,
        model: row.model,
        timeout_sec: row.timeout_sec,
        max_concurrency: row.max_concurrency,
        enabled: row.enabled,
        settings: row.settings,
      }),
    });
    message.value = `${channelMeta[row.channel].title} 配置已保存。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function saveSecret(row: any) {
  if (!confirm(`${row.secret_configured ? "轮换" : "保存"} ${channelMeta[row.channel].title} 的 API Key？保存后不会再次显示。`)) return;
  acting.value = `secret:${row.channel}`;
  try {
    await api(`/api/v1/admin/integrations/${row.channel}/secret`, { method: "PUT", body: jsonBody({ secret: secrets.value[row.channel] }) });
    secrets.value[row.channel] = "";
    message.value = `${channelMeta[row.channel].title} 密钥已加密保存。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function clearSecret(row: any) {
  if (!confirm(`移除 ${channelMeta[row.channel].title} 的密钥？启用状态不会自动关闭，但调用会安全降级。`)) return;
  acting.value = `secret:${row.channel}`;
  try {
    await api(`/api/v1/admin/integrations/${row.channel}/secret`, { method: "DELETE" });
    message.value = `${channelMeta[row.channel].title} 密钥已移除。`;
    await refresh(true);
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

async function testConnection(row: any) {
  acting.value = `test:${row.channel}`;
  try {
    results.value[row.channel] = await api(`/api/v1/admin/integrations/${row.channel}/test`, { method: "POST" });
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason);
  } finally { acting.value = ""; }
}

const { loading, refreshing, error, lastUpdated, refresh } = usePolling(load, { intervalMs: 30_000 });
</script>

<template>
  <PageHeader title="外部 API 集成" :description="`四个通道严格隔离；${configuredCount}/${rows.length || 4} 个通道当前可用。连通性测试只发送固定合成文本。`" :last-updated="lastUpdated" :refreshing="refreshing" refreshable @refresh="refresh(true)" />
  <FeedbackBanner kind="warning">外部非本机地址必须使用 HTTPS。密钥仅能写入或轮换，接口、日志和审计永不回显。</FeedbackBanner>
  <FeedbackBanner v-if="error" kind="error">{{ error }}</FeedbackBanner>
  <FeedbackBanner v-if="message" kind="success" dismissible @dismiss="message=''">{{ message }}</FeedbackBanner>
  <div v-if="loading" class="card loading-panel">正在读取加密集成配置…</div>

  <div v-else class="integration-grid">
    <section class="card integration-card" v-for="row in rows" :key="row.channel">
      <div class="integration-head">
        <div><small>{{ row.channel }}</small><h2>{{ channelMeta[row.channel].title }}</h2><p>{{ channelMeta[row.channel].description }}</p></div>
        <StatusBadge :status="row.enabled ? 'active' : 'disabled'" />
      </div>

      <div class="form-grid">
        <label>Provider
          <select class="input" v-model="row.provider" :disabled="user.role !== 'admin'"><option v-for="item in channelMeta[row.channel].providers" :key="item">{{ item }}</option></select>
        </label>
        <label>Model
          <input class="input" v-model.trim="row.model" :disabled="user.role !== 'admin' || row.channel === 'crossref' || row.provider === 'mock'" placeholder="模型 ID" />
        </label>
        <label class="span-2">Base URL
          <input class="input" type="url" v-model.trim="row.base_url" :disabled="user.role !== 'admin' || row.provider === 'mock'" placeholder="https://…" />
        </label>
        <label>超时（秒）<input class="input" type="number" min="1" max="300" v-model.number="row.timeout_sec" :disabled="user.role !== 'admin'" /></label>
        <label>最大并发<input class="input" type="number" min="1" max="32" v-model.number="row.max_concurrency" :disabled="user.role !== 'admin'" /></label>
      </div>

      <div v-if="row.channel === 'report_llm'" class="settings-panel">
        <h3>生成参数</h3><div class="form-grid">
          <label>最大输出 tokens<input class="input" type="number" min="1" max="10000" v-model.number="row.settings.max_tokens" :disabled="user.role !== 'admin'" /></label>
          <label>Temperature<input class="input" type="number" min="0" max="2" step="0.1" v-model.number="row.settings.temperature" :disabled="user.role !== 'admin'" /></label>
          <label>最小调用间隔（秒）<input class="input" type="number" min="0" max="60" step="0.1" v-model.number="row.settings.min_interval_sec" :disabled="user.role !== 'admin'" /></label>
          <label v-if="['anthropic','claude'].includes(row.provider)">Anthropic API 版本<input class="input" v-model.trim="row.settings.anthropic_version" :disabled="user.role !== 'admin'" /></label>
        </div>
      </div>
      <div v-else-if="row.channel === 'embedding'" class="settings-panel">
        <h3>向量参数</h3><div class="form-grid">
          <label>向量维度<input class="input" type="number" min="64" max="3072" v-model.number="row.settings.dimensions" :disabled="user.role !== 'admin'" /></label>
          <label>批大小<input class="input" type="number" min="1" max="512" v-model.number="row.settings.batch_size" :disabled="user.role !== 'admin'" /></label>
          <label class="span-2">输入范围<select class="input" v-model="row.settings.input_scope" :disabled="user.role !== 'admin'"><option value="processed_chunks">治理后的摘要 chunks</option><option value="fulltext_chunks">本地治理全文 chunks（授权状态另行核验）</option></select></label>
        </div>
      </div>
      <div v-else-if="row.channel === 'evaluation'" class="settings-panel">
        <h3>评估参数</h3><div class="form-grid">
          <label>最大输出 tokens<input class="input" type="number" min="1" max="10000" v-model.number="row.settings.max_tokens" :disabled="user.role !== 'admin'" /></label>
          <label>Temperature<input class="input" type="number" min="0" max="2" step="0.1" v-model.number="row.settings.temperature" :disabled="user.role !== 'admin'" /></label>
          <label>最小调用间隔（秒）<input class="input" type="number" min="0" max="60" step="0.1" v-model.number="row.settings.min_interval_sec" :disabled="user.role !== 'admin'" /></label>
          <label class="fixed-setting"><input type="checkbox" :checked="false" disabled /> send_fulltext 固定关闭</label>
        </div>
      </div>

      <label v-if="user.role === 'admin'" class="switch-row"><input type="checkbox" v-model="row.enabled" /><span>启用此通道</span></label>
      <div v-if="user.role === 'admin'" class="toolbar integration-actions">
        <button class="btn primary" :disabled="!!acting" @click="save(row)">{{ acting === `save:${row.channel}` ? "保存中…" : "保存配置" }}</button>
        <button class="btn" :disabled="!!acting" @click="testConnection(row)">{{ acting === `test:${row.channel}` ? "测试中…" : "合成请求测试" }}</button>
      </div>

      <div v-if="row.channel !== 'crossref'" class="secret-panel">
        <div><strong>API Key</strong><StatusBadge :status="row.secret_configured ? 'current' : 'missing'" :label="row.secret_configured ? '已配置' : '未配置'" /><small v-if="row.secret_updated_at">最近轮换：{{ row.secret_updated_at }}</small></div>
        <div v-if="user.role === 'admin'" class="toolbar">
          <input class="input" type="password" v-model="secrets[row.channel]" autocomplete="new-password" placeholder="输入新密钥；保存后清空且不回显" />
          <button class="btn" :disabled="!secrets[row.channel] || !!acting" @click="saveSecret(row)">{{ row.secret_configured ? "轮换" : "加密保存" }}</button>
          <button v-if="row.secret_configured" class="btn danger" :disabled="!!acting" @click="clearSecret(row)">移除</button>
        </div>
      </div>

      <FeedbackBanner v-if="results[row.channel]" :kind="results[row.channel].ok ? 'success' : 'error'">
        <strong>{{ results[row.channel].ok ? "连接成功" : "连接失败" }}</strong>
        <span>{{ results[row.channel].latency_ms != null ? `${results[row.channel].latency_ms} ms` : "" }} {{ results[row.channel].message || results[row.channel].tested_with || "" }}</span>
        <code v-if="results[row.channel].error_code">{{ results[row.channel].error_code }}</code>
      </FeedbackBanner>
    </section>
  </div>
</template>
