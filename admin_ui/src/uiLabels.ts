export const roleLabels: Record<string, string> = {
  admin: "系统管理员",
  curator: "资料编辑",
  reviewer: "内容审核",
  viewer: "只读成员",
};

export const topicLabels: Record<string, string> = {
  bp_categories: "血压参考范围",
  home_bp_monitoring: "居家血压测量",
  emergency: "紧急情况提示",
  cuffless_ppg_limitations: "无袖带与 PPG 局限",
  validated_devices: "经验证的测量设备",
  lifestyle: "生活方式",
  special_population: "特殊人群",
  measurement_quality: "测量质量",
  medication_safety: "用药安全",
  disclaimer: "使用边界说明",
  research_context: "研究背景",
};

export const allowedUseLabels: Record<string, string> = {
  bp_category_reference: "解释血压参考范围",
  home_bp_monitoring: "指导居家测量",
  remeasurement: "建议规范复测",
  lifestyle: "生活方式建议",
  special_population: "特殊人群说明",
  medication_safety: "用药安全提醒",
  cuffless_ppg_limitations: "说明 PPG 与无袖带局限",
  device_advice: "测量设备建议",
  signal_quality: "解释信号质量",
  research_background: "补充研究背景",
  disclaimer: "展示使用边界",
  emergency_alert: "紧急情况提示",
  arrhythmia_screening: "建议进一步排查心律问题",
};

export const evidenceClassLabels: Record<string, string> = {
  guideline: "临床指南",
  official_health_education: "官方健康教育",
  patient_education: "患者教育资料",
  research_context: "研究背景资料",
  review: "综述",
  safety_rule: "安全规则",
  scientific_statement: "科学声明",
  validation_standard: "验证标准",
};

export const sourceTypeLabels: Record<string, string> = {
  guideline: "指南",
  official_health_education: "官方健康教育",
  patient_education: "患者教育",
  research_article: "研究论文",
  randomized_controlled_trial: "随机对照研究",
  review: "综述",
  systematic_review: "系统综述",
  scientific_statement: "科学声明",
  validation_standard: "验证标准",
  safety_rule: "安全规则",
};

export const regionLabels: Record<string, string> = {
  global: "全球",
  CN: "中国",
  US: "美国",
  UK: "英国",
  EU: "欧洲",
  CA: "加拿大",
  AHA: "美国心脏协会",
};

export const artifactMeta: Record<string, { title: string; description: string }> = {
  screening: { title: "资料入选结果", description: "确认哪些资料可以进入内容库。" },
  chunks: { title: "可检索内容", description: "把已审核资料整理为可用于回答的内容片段。" },
  hashing_processed: { title: "基础检索", description: "断网时仍可使用的本地检索能力。" },
  chroma_bge: { title: "本地智能检索", description: "使用本地模型理解问题与资料的相关性。" },
  openai_processed: { title: "云端摘要检索", description: "使用云端向量服务检索已治理摘要。" },
  fulltext_local: { title: "本地全文检索", description: "显示全文是否可在本机检索；不代表版权授权已经通过。" },
  openai_fulltext: { title: "云端全文检索", description: "显示全文是否已同步到云端检索；不代表版权授权已经通过。" },
  quality_gate: { title: "质量检查报告", description: "确认资料、回答、安全边界和性能仍符合要求。" },
};

export const jobLabels: Record<string, string> = {
  rescreen: "更新资料入选结果",
  ingest_chunks: "更新可检索内容",
  build_chroma: "更新本地智能检索",
  build_fulltext: "更新本地全文检索",
  build_openai_processed: "同步云端摘要检索",
  build_openai_fulltext: "同步云端全文检索",
  kb_audit: "检查资料库完整性",
  quality_gate: "运行完整质量检查",
  retrieval_evaluation: "检查资料检索效果",
  report_evaluation: "检查报告内容质量",
  api_experiment: "检查接口运行表现",
  validate_config_draft: "验证规则草稿",
  rollback_config_revision: "验证历史版本恢复",
};

export const configMeta: Record<string, { title: string; description: string }> = {
  settings: { title: "系统运行方式", description: "报告生成、检索方式和离线降级设置。" },
  screening_rules: { title: "进一步排查提示", description: "控制何时提示用户寻求专业检查，不产生诊断结论。" },
  safety_terms: { title: "安全表达边界", description: "拦截诊断、调药、错误安抚等不安全表达。" },
  bp_thresholds: { title: "血压与信号参考范围", description: "血压范围、信号质量和紧急情况参考值。" },
  advisor_questions: { title: "随访提问内容", description: "管理渐进式提问、解释原因和可跳过选项。" },
  field_mapping: { title: "数据字段兼容", description: "兼容不同调用方传入的字段名称。" },
};

export const fieldLabels: Record<string, string> = {
  app: "应用信息",
  generation: "报告生成",
  retrieval: "资料检索",
  safety: "安全边界",
  screening: "进一步排查",
  evaluation: "质量评测",
  quality: "信号质量",
  AHA: "AHA 血压参考",
  CN: "中国血压参考",
  emergency: "紧急情况参考",
  questions: "提问内容",
  conditions: "触发条件",
  enabled: "是否启用",
  diagnostic_patterns: "诊断性表达拦截",
  medication_change_patterns: "调药表达拦截",
  required_disclaimer_terms: "必须出现的边界说明",
};

export const channelLabels: Record<string, { title: string; description: string }> = {
  report_llm: { title: "智能报告服务", description: "辅助生成保守、可追溯的健康解释；不可用时自动使用安全模板。" },
  embedding: { title: "云端语义检索", description: "让资料检索更贴近用户问题，仅处理经过治理的内容。" },
  evaluation: { title: "自动质量评审", description: "只检查固定的匿名测试样例，始终不发送知识库全文。" },
  crossref: { title: "文献信息补全", description: "从公开书目服务补充 DOI、期刊和出版信息。" },
};

export const providerLabels: Record<string, string> = {
  mock: "本地安全模板",
  deepseek: "DeepSeek",
  anthropic: "Anthropic",
  claude: "Claude",
  openai: "OpenAI",
  openai_compatible: "兼容接口",
  crossref: "Crossref",
};

export const reportSystemLabels: Record<string, string> = {
  llm_only_mock: "仅生成模型",
  rag_only_mock: "资料检索增强",
  rule_rag_safety: "安全规则 + 资料检索",
};

export const auditActionLabels: Record<string, string> = {
  "auth.login": "登录后台",
  "auth.logout": "退出后台",
  "user.create": "创建成员",
  "user.update": "调整成员权限",
  "api_client.create": "创建系统接入凭证",
  "api_client.revoke": "停用系统接入凭证",
  "integration.update": "更新外部服务设置",
  "integration.secret.update": "更新外部服务密钥",
  "integration.secret.migrate": "迁移外部服务密钥",
  "integration.secret.rotate": "更换外部服务密钥",
  "integration.secret.delete": "移除外部服务密钥",
  "integration.test": "测试外部服务",
  "job.create": "安排后台处理",
  "job.enqueue": "安排后台处理",
  "job.retry": "重新执行后台处理",
  "job.cancel": "取消后台处理",
  "library.source.update": "更新资料",
  "library.source.trash": "资料移入回收站",
  "library.draft.create": "创建资料草稿",
  "library.draft.validate": "校验资料草稿",
  "library.draft.publish": "发布资料",
  "config.draft.create": "创建规则草稿",
  "config.draft.publish": "发布规则",
  "config.revision.rollback": "恢复规则历史版本",
  "library.attach_fulltext": "保存资料全文",
  "library.autofill": "识别资料信息",
  "library.autofill_batch": "批量识别资料信息",
  "library.autofill_pdf": "从 PDF 识别资料信息",
  "library.check_duplicates": "检查重复资料",
  "library.create_source": "添加资料",
  "library.create_sources_batch": "批量添加资料",
  "library.delete_source": "资料移入回收站",
  "library.detach_fulltext": "移除资料全文",
  "library.ingest": "更新可检索内容",
  "library.purge_source": "永久删除资料",
  "library.restore_source": "恢复资料",
  "library.set_include": "调整资料使用状态",
  "library.update_source": "更新资料",
  "admin.failed.update_integration_endpoint": "外部服务设置失败",
};

export const resourceLabels: Record<string, string> = {
  auth: "登录会话",
  user: "成员账号",
  api_client: "系统接入凭证",
  integration: "外部服务",
  job: "后台处理",
  library_source: "资料",
  library_draft: "资料草稿",
  config_draft: "规则草稿",
  config_revision: "规则版本",
  admin_api: "后台服务",
  admin_job: "后台处理",
  admin_session: "登录会话",
  integration_profile: "外部服务",
  library_api: "资料管理",
};

export function displayLabel(labels: Record<string, string>, value?: string | null, fallback = "未设置") {
  if (!value) return fallback;
  return labels[value] || value.replace(/_/g, " ");
}

export function displayList(labels: Record<string, string>, values?: string[] | null, empty = "未设置") {
  if (!values?.length) return empty;
  return values.map((value) => displayLabel(labels, value)).join("、");
}

export function configSummary(content: Record<string, unknown> = {}) {
  return Object.entries(content).map(([key, value]) => {
    let summary = "";
    if (Array.isArray(value)) summary = `${value.length} 项`;
    else if (value && typeof value === "object") summary = `${Object.keys(value).length} 组设置`;
    else if (typeof value === "boolean") summary = value ? "已开启" : "已关闭";
    else summary = String(value ?? "未设置");
    return { key, label: displayLabel(fieldLabels, key), summary };
  });
}
