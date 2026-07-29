<script setup lang="ts">
import { computed, onMounted, onUnmounted, provide, ref } from "vue";
import { RouterLink, RouterView, useRoute } from "vue-router";
import { api, jsonBody } from "./api";
import { roleLabels } from "./uiLabels";

type User = { id: string; username: string; role: string; auth_disabled?: boolean };

const route = useRoute();
const user = ref<User | null>(null);
const loading = ref(true);
const loginBusy = ref(false);
const loginError = ref("");
const username = ref("");
const password = ref("");

const modules = [
  { path: "/", label: "工作概览", icon: "⌂", hint: "待办与整体状态" },
  { path: "/library", label: "资料管理", icon: "文", hint: "资料、全文与审核" },
  { path: "/knowledge", label: "内容更新", icon: "↻", hint: "让最新资料进入检索" },
  { path: "/retrieval", label: "回答预览", icon: "⌕", hint: "看看系统会引用什么" },
  { path: "/config", label: "规则设置", icon: "规", hint: "医学规则与表达边界" },
  { path: "/integrations", label: "服务设置", icon: "联", hint: "模型与文献服务" },
  { path: "/quality", label: "质量检查", icon: "✓", hint: "检索、报告与安全" },
  { path: "/jobs", label: "处理记录", icon: "时", hint: "后台更新进度" },
  { path: "/access", label: "成员与安全", icon: "人", hint: "账号、接入与日志" },
];
const currentModule = computed(() => modules.find((item) => item.path === route.path) || modules[0]);

provide("adminUser", user);

async function loadUser() {
  try { user.value = await api<User>("/api/v1/admin/auth/me"); }
  catch { user.value = null; }
  finally { loading.value = false; }
}

async function login() {
  loginError.value = "";
  loginBusy.value = true;
  try {
    const result = await api<{ user: User }>("/api/v1/admin/auth/login", {
      method: "POST", body: jsonBody({ username: username.value, password: password.value }),
    });
    user.value = result.user;
    password.value = "";
  } catch (error) { loginError.value = (error as Error).message; }
  finally { loginBusy.value = false; }
}

async function logout() {
  try { await api("/api/v1/admin/auth/logout", { method: "POST" }); }
  finally { user.value = null; }
}

function expireSession() {
  user.value = null;
  loginError.value = "登录已失效，请重新登录";
}

onMounted(() => {
  window.addEventListener("admin:unauthorized", expireSession);
  void loadUser();
});
onUnmounted(() => window.removeEventListener("admin:unauthorized", expireSession));
</script>

<template>
  <div v-if="loading" class="login-page"><div class="login-card">正在加载后台…</div></div>
  <div v-else-if="!user" class="login-page">
    <div class="login-card">
      <div class="login-mark">循证</div>
      <h1>高血压健康解释后台</h1>
      <div class="muted">管理资料、规则和质量检查，仅供内部团队使用。</div>
      <form @submit.prevent="login">
        <label>账号<input class="input" v-model.trim="username" autocomplete="username" required autofocus /></label>
        <label>密码<input class="input" type="password" v-model="password" autocomplete="current-password" required /></label>
        <div v-if="loginError" class="error">{{ loginError }}</div>
        <button class="btn primary login-submit" type="submit" :disabled="loginBusy">{{ loginBusy ? "正在进入…" : "进入后台" }}</button>
      </form>
      <p class="login-boundary">内容仅用于健康解释，不用于诊断、调药或验证 PPG 血压估算准确性。</p>
    </div>
  </div>
  <div v-else class="layout">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark">循</span>
        <span>循证内容中心<small>高血压健康解释</small></span>
      </div>
      <nav class="nav">
        <RouterLink v-for="item in modules" :key="item.path" :to="item.path" :class="{ 'router-link-active': route.path === item.path }">
          <span class="nav-icon">{{ item.icon }}</span>
          <span class="nav-copy"><strong>{{ item.label }}</strong><small>{{ item.hint }}</small></span>
        </RouterLink>
      </nav>
      <div class="sidebar-boundary">
        <strong>使用边界</strong>
        <span>不用于诊断、调药或替代袖带血压测量。</span>
      </div>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="topbar-note"><span class="system-dot"></span><span><strong>{{ currentModule.label }}</strong><small>{{ currentModule.hint }}</small></span></div>
        <div class="user">
          <span class="user-avatar">{{ user.username.slice(0, 1).toUpperCase() }}</span>
          <span class="user-name"><strong>{{ user.username }}</strong><small>{{ roleLabels[user.role] || user.role }}</small></span>
          <button class="btn ghost" @click="logout">退出</button>
        </div>
      </header>
      <RouterView />
    </main>
  </div>
</template>
