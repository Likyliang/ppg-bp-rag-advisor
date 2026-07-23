import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import DashboardView from "./views/DashboardView.vue";
import LibraryView from "./views/LibraryView.vue";
import KnowledgeView from "./views/KnowledgeView.vue";
import RetrievalView from "./views/RetrievalView.vue";
import ConfigView from "./views/ConfigView.vue";
import IntegrationsView from "./views/IntegrationsView.vue";
import QualityView from "./views/QualityView.vue";
import JobsView from "./views/JobsView.vue";
import AccessAuditView from "./views/AccessAuditView.vue";
import "./style.css";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: "/", component: DashboardView },
    { path: "/library", component: LibraryView },
    { path: "/knowledge", component: KnowledgeView },
    { path: "/retrieval", component: RetrievalView },
    { path: "/config", component: ConfigView },
    { path: "/integrations", component: IntegrationsView },
    { path: "/quality", component: QualityView },
    { path: "/jobs", component: JobsView },
    { path: "/access", component: AccessAuditView },
  ],
});

createApp(App).use(router).mount("#app");
