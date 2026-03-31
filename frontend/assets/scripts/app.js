const state = {
  environments: [],
  environment: "",
  connected: false,
  branding: {
    logoUrl: "",
    iconUrl: "",
    title: "Suite Testes Consignado",
    subtitle: "",
  },
  options: {
    agreements: [],
    products: [],
    saleModalities: [],
    withdrawTypes: [],
  },
  selections: {
    agreementId: "",
    productId: "",
    saleModalityId: "",
    withdrawTypeId: "",
  },
  processorCode: "",
  preview: null,
  warnings: [],
  simulation: null,
  simulationRaw: null,
  proposal: null,
  proposalRaw: null,
  proposalGenerated: null,
  simulationStatus: "idle",
  proposalStatus: "idle",
  proposalCooldown: false,
  nameMode: "manual",
  phoneMode: "manual",
  proposalHistory: [],
  observabilitySummary: buildEmptyObservabilitySummary(),
  flowConfigs: {},
  expandedFlowRows: {},
  loadingHistoryFlows: {},
  historyFlowErrors: {},
  executingHistoryRows: {},
  batchCancelled: false,
  batchExecutionActive: false,
};

function buildEmptyObservabilitySummary() {
  return {
    proposalsWithExecutions: 0,
    totalExecutions: 0,
    completedExecutions: 0,
    failedExecutions: 0,
    manualExecutions: 0,
    waitingExecutions: 0,
    cancelledExecutions: 0,
    totalStageResults: 0,
    totalHttpCalls: 0,
    totalDbChecks: 0,
    averageDurationMs: 0,
    latestFinishedAt: "",
  };
}

const dom = {};
let sectionObserver = null;
let headerResizeObserver = null;
const EXECUTION_STATUS_POLL_INTERVAL_MS = 5000;

document.addEventListener("DOMContentLoaded", async () => {
  cacheDom();
  bindEvents();
  restoreSidebarState();
  applyStoredTheme();
  updateModeButtons("name", state.nameMode);
  updateModeButtons("phone", state.phoneMode);
  await Promise.all([loadAppConfig(), loadEnvironments(), clearServerHistory()]);
  setupSectionObserver();
  renderAll();
  setupLayoutSync();
});

function cacheDom() {
  dom.appFavicon = document.getElementById("appFavicon");
  dom.sidebarLogo = document.getElementById("sidebarLogo");
  dom.sidebarBrandTop = document.getElementById("sidebarBrandTop");
  dom.appHeader = document.getElementById("appHeader");

  dom.headerSidebarToggle = document.getElementById("headerSidebarToggle");
  dom.sidebarOverlay = document.getElementById("sidebarOverlay");
  dom.flowColHeader = document.getElementById("flowColHeader");
  dom.navItems = Array.from(document.querySelectorAll("[data-scroll-target]"));
  dom.pageSections = Array.from(document.querySelectorAll(".page-section"));
  dom.appContent = document.querySelector(".app-content");

  dom.environmentButtons = document.getElementById("environmentButtons");
  dom.connectButton = document.getElementById("connectButton");
  dom.agreementSelect = document.getElementById("agreementSelect");
  dom.productSelect = document.getElementById("productSelect");
  dom.saleModalitySelect = document.getElementById("saleModalitySelect");
  dom.withdrawTypeSelect = document.getElementById("withdrawTypeSelect");
  dom.previewButton = document.getElementById("previewButton");
  dom.simulateButton = document.getElementById("simulateButton");
  dom.proposalButton = document.getElementById("proposalButton");
  dom.proposalStatusBanner = document.getElementById("proposalStatusBanner");
  dom.proposalActionCard = document.querySelector(".proposal-action-card");
  dom.nextProposalPanel = document.getElementById("nextProposalPanel");
  dom.newProposalButton = document.getElementById("newProposalButton");

  dom.summaryEnvironment = document.getElementById("summaryEnvironment");
  dom.summaryAgreement = document.getElementById("summaryAgreement");
  dom.summaryProduct = document.getElementById("summaryProduct");
  dom.summaryProcessor = document.getElementById("summaryProcessor");

  dom.sidebarStatusText = document.getElementById("sidebarStatusText");
  dom.sidebarProcessor = document.getElementById("sidebarProcessor");
  dom.sidebarProposalCode = document.getElementById("sidebarProposalCode");
  dom.sidebarContractCode = document.getElementById("sidebarContractCode");
  dom.footerStatusText = document.getElementById("footerStatusText");

  dom.clientNameInput = document.getElementById("clientNameInput");
  dom.clientDocumentInput = document.getElementById("clientDocumentInput");
  dom.clientPhoneInput = document.getElementById("clientPhoneInput");
  dom.documentHelper = document.getElementById("documentHelper");
  dom.generateNameButton = document.getElementById("generateNameButton");
  dom.generatePhoneButton = document.getElementById("generatePhoneButton");
  dom.nameSuggestionBadge = document.getElementById("nameSuggestionBadge");
  dom.useSuggestedNameButton = document.getElementById("useSuggestedNameButton");

  dom.previewPlaceholder = document.getElementById("previewPlaceholder");
  dom.previewCard = document.getElementById("previewCard");
  dom.previewProcessorBadge = document.getElementById("previewProcessorBadge");
  dom.previewWorksheetTitle = document.getElementById("previewWorksheetTitle");
  dom.previewBalanceValue = document.getElementById("previewBalanceValue");
  dom.previewCpfValue = document.getElementById("previewCpfValue");
  dom.previewMatricula = document.getElementById("previewMatricula");
  dom.previewHelperText = document.getElementById("previewHelperText");
  dom.previewRecordControls = document.getElementById("previewRecordControls");
  dom.previewRecordCounter = document.getElementById("previewRecordCounter");
  dom.nextPreviewRecordButton = document.getElementById("nextPreviewRecordButton");

  dom.allowCipFallbackInput = document.getElementById("allowCipFallbackInput");
  dom.cipPanel = document.getElementById("cipPanel");
  dom.zetraPanel = document.getElementById("zetraPanel");
  dom.serproPanel = document.getElementById("serproPanel");
  dom.ccbPanel = document.getElementById("ccbPanel");
  dom.zetraHint = document.getElementById("zetraHint");
  dom.benefitNumberInput = document.getElementById("benefitNumberInput");
  dom.userPasswordInput = document.getElementById("userPasswordInput");
  dom.serproAgencyIdInput = document.getElementById("serproAgencyIdInput");
  dom.serproAgencySubIdInput = document.getElementById("serproAgencySubIdInput");
  dom.serproAgencySubUpagIdInput = document.getElementById("serproAgencySubUpagIdInput");
  dom.sponsorBenefitNumberInput = document.getElementById("sponsorBenefitNumberInput");
  dom.originalCcbCodeInput = document.getElementById("originalCcbCodeInput");
  dom.originalCcbOriginInput = document.getElementById("originalCcbOriginInput");

  dom.statusBanner = document.getElementById("statusBanner");
  dom.warningList = document.getElementById("warningList");

  dom.proposalSimulationId = document.getElementById("proposalSimulationId");
  dom.proposalMainDocument = document.getElementById("proposalMainDocument");
  dom.proposalBenefitPreview = document.getElementById("proposalBenefitPreview");
  dom.proposalDocumentPreview = document.getElementById("proposalDocumentPreview");
  dom.proposalEmailPreview = document.getElementById("proposalEmailPreview");

  dom.contractCard = document.getElementById("contractCard");
  dom.contractCode = document.getElementById("contractCode");
  dom.contractNarrative = document.getElementById("contractNarrative");
  dom.resultRequestedValue = document.getElementById("resultRequestedValue");
  dom.resultInstallmentValue = document.getElementById("resultInstallmentValue");
  dom.resultDeadline = document.getElementById("resultDeadline");
  dom.resultMarginValue = document.getElementById("resultMarginValue");

  dom.proposalCard = document.getElementById("proposalCard");
  dom.proposalCode = document.getElementById("proposalCode");
  dom.proposalNarrative = document.getElementById("proposalNarrative");
  dom.proposalId = document.getElementById("proposalId");
  dom.proposalDocumentType = document.getElementById("proposalDocumentType");
  dom.proposalDocumentMasked = document.getElementById("proposalDocumentMasked");
  dom.proposalEmail = document.getElementById("proposalEmail");

  dom.errorDetails = document.getElementById("errorDetails");
  dom.errorDetailText = document.getElementById("errorDetailText");

  dom.historyTableBody = document.getElementById("historyTableBody");
  dom.historyEmptyState = document.getElementById("historyEmptyState");
  dom.historyTableWrapper = document.getElementById("historyTableWrapper");
  dom.historyBatchAction = document.getElementById("historyBatchAction");
  dom.testAllButton = document.getElementById("testAllButton");
  dom.cancelAllButton = document.getElementById("cancelAllButton");
  dom.resetAllButton = document.getElementById("resetAllButton");

  dom.observabilitySummaryStrip = document.getElementById("observabilitySummaryStrip");
  dom.observabilityEmptyState = document.getElementById("observabilityEmptyState");
  dom.observabilityProposalList = document.getElementById("observabilityProposalList");
  dom.generateReportButton = document.getElementById("generateReportButton");

  dom.flowModal = document.getElementById("flowModal");
  dom.flowModalBackdrop = document.getElementById("flowModalBackdrop");
  dom.flowModalSubtitle = document.getElementById("flowModalSubtitle");
  dom.flowModalBody = document.getElementById("flowModalBody");
  dom.flowModalClose = document.getElementById("flowModalClose");
  dom.flowModalCancel = document.getElementById("flowModalCancel");
  dom.flowModalConfirm = document.getElementById("flowModalConfirm");

  dom.executionFinishedModal = document.getElementById("executionFinishedModal");
  dom.executionFinishedModalBackdrop = document.getElementById("executionFinishedModalBackdrop");
  dom.executionFinishedModalTitle = document.getElementById("executionFinishedModalTitle");
  dom.executionFinishedModalMessage = document.getElementById("executionFinishedModalMessage");
  dom.executionFinishedModalClose = document.getElementById("executionFinishedModalClose");
  dom.executionFinishedModalConfirm = document.getElementById("executionFinishedModalConfirm");
}

function bindEvents() {
  dom.environmentButtons.addEventListener("click", handleEnvironmentClick);
  dom.connectButton.addEventListener("click", handleConnect);
  dom.previewButton.addEventListener("click", handlePreview);
  dom.nextPreviewRecordButton.addEventListener("click", handleNextPreviewRecord);
  dom.simulateButton.addEventListener("click", handleSimulate);
  dom.proposalButton.addEventListener("click", handleProposal);
  dom.newProposalButton.addEventListener("click", handleStartNextProposal);
  dom.testAllButton.addEventListener("click", handleTestAll);
  dom.cancelAllButton.addEventListener("click", cancelAllExecutions);
  dom.resetAllButton.addEventListener("click", resetAllExecutions);
  if (dom.generateReportButton) {
    dom.generateReportButton.addEventListener("click", handleGenerateReport);
  }
  dom.flowModalBackdrop.addEventListener("click", closeFlowModal);
  dom.flowModalClose.addEventListener("click", closeFlowModal);
  dom.flowModalCancel.addEventListener("click", handleFlowModalCancel);
  dom.flowModalConfirm.addEventListener("click", handleFlowModalConfirm);
  dom.executionFinishedModalBackdrop.addEventListener("click", closeExecutionFinishedModal);
  dom.executionFinishedModalClose.addEventListener("click", closeExecutionFinishedModal);
  dom.executionFinishedModalConfirm.addEventListener("click", closeExecutionFinishedModal);

  dom.headerSidebarToggle.addEventListener("click", toggleSidebar);

  if (dom.sidebarOverlay) {
    dom.sidebarOverlay.addEventListener("click", closeMobileSidebar);
  }

  dom.navItems.forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.dataset.scrollTarget;
      const section = document.getElementById(targetId);
      if (section) {
        scrollSectionToTop(targetId);
      }
      if (window.innerWidth <= 980) {
        closeMobileSidebar();
      }
    });
  });

  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    button.addEventListener("click", () => applyTheme(button.dataset.themeValue));
  });

  [dom.agreementSelect, dom.productSelect, dom.saleModalitySelect, dom.withdrawTypeSelect].forEach((select) => {
    select.addEventListener("change", handleSelectionChange);
  });

  document.querySelectorAll("[data-name-mode]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.nameMode = button.dataset.nameMode;
      updateModeButtons("name", state.nameMode);
      if (state.nameMode === "faker") {
        await fillWithFaker("name");
      }
      clearExecutionState();
      renderWarnings();
      renderResults();
      renderProposalWorkspace();
      renderActionState();
      renderStatusCopy();
    });
  });

  document.querySelectorAll("[data-phone-mode]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.phoneMode = button.dataset.phoneMode;
      updateModeButtons("phone", state.phoneMode);
      if (state.phoneMode === "faker") {
        await fillWithFaker("phone");
      }
      clearExecutionState();
      renderWarnings();
      renderResults();
      renderProposalWorkspace();
      renderActionState();
      renderStatusCopy();
    });
  });

  dom.generateNameButton.addEventListener("click", () => fillWithFaker("name"));
  dom.generatePhoneButton.addEventListener("click", () => fillWithFaker("phone"));
  dom.useSuggestedNameButton.addEventListener("click", () => {
    if (!state.preview?.nome) {
      return;
    }
    dom.clientNameInput.value = state.preview.nome;
    state.nameMode = "manual";
    updateModeButtons("name", state.nameMode);
    clearExecutionState();
    setStatusBanner("Nome sugerido aplicado ao cliente.", "info");
    renderWarnings();
    renderResults();
    renderProposalWorkspace();
    renderActionState();
    renderStatusCopy();
  });

  [
    dom.clientNameInput,
    dom.clientPhoneInput,
    dom.benefitNumberInput,
    dom.userPasswordInput,
    dom.serproAgencyIdInput,
    dom.serproAgencySubIdInput,
    dom.serproAgencySubUpagIdInput,
    dom.sponsorBenefitNumberInput,
    dom.originalCcbCodeInput,
    dom.originalCcbOriginInput,
  ].forEach((field) => {
    field.addEventListener("input", () => {
      clearExecutionState();
      renderAdvancedPanels();
      renderWarnings();
      renderResults();
      renderProposalWorkspace();
      renderActionState();
      renderStatusCopy();
    });
  });

  dom.allowCipFallbackInput.addEventListener("change", () => {
    clearExecutionState();
    renderWarnings();
    renderResults();
    renderProposalWorkspace();
    renderActionState();
    renderStatusCopy();
  });

  setupCopyButtons();
}

async function loadAppConfig() {
  try {
    const payload = await apiRequest("/api/app-config");
    state.branding = {
      ...state.branding,
      ...(payload.branding || {}),
    };
    applyBranding();
  } catch (error) {
    applyBranding();
  }
}

async function loadEnvironments() {
  try {
    const payload = await apiRequest("/api/environments");
    state.environments = payload.items || [];
    if (!state.environment && state.environments.length) {
      state.environment = state.environments[0].key;
    }
  } catch (error) {
    setStatusBanner("Nao consegui carregar os ambientes.", "error");
    showTechnicalDetails(error);
  }
}

function applyBranding() {
  if (state.branding.iconUrl) {
    dom.appFavicon.href = state.branding.iconUrl;
  }

  document.title = state.branding.title || "Suite Consignado";
}

function renderAll() {
  renderEnvironmentButtons();
  renderSelectOptions();
  renderSummary();
  renderPreview();
  renderAdvancedPanels();
  renderWarnings();
  renderResults();
  renderProposalWorkspace();
  renderProposalFeedback();
  renderNextProposalAction();
  renderConnectButton();
  renderActionState();
  renderStatusCopy();
  renderJourneyIndicators();
  renderStepSubtexts();
  renderSectionLocks();
  renderProcessorContextBlock();
  renderHistory();
  renderObservability();
  syncSidebarBrandHeight();
}

function renderEnvironmentButtons() {
  dom.environmentButtons.innerHTML = "";
  state.environments.forEach((environment) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "segmented-btn environment-btn" + (environment.key === state.environment ? " active is-active" : "");
    button.dataset.environment = environment.key;
    button.textContent = environment.label;
    dom.environmentButtons.appendChild(button);
  });
}

function renderSelectOptions() {
  populateSelect(dom.agreementSelect, state.options.agreements, state.selections.agreementId, "Selecione");
  populateSelect(dom.productSelect, state.options.products, state.selections.productId, "Selecione");
  populateSelect(dom.saleModalitySelect, state.options.saleModalities, state.selections.saleModalityId, "Selecione");
  populateSelect(dom.withdrawTypeSelect, state.options.withdrawTypes, state.selections.withdrawTypeId, "Selecione");

  [dom.agreementSelect, dom.productSelect, dom.saleModalitySelect, dom.withdrawTypeSelect].forEach((select) => {
    select.disabled = !state.connected;
  });
}

function populateSelect(select, items, selectedValue, placeholder) {
  const previous = selectedValue !== undefined && selectedValue !== null ? selectedValue : select.value || "";
  select.innerHTML = "";

  const placeholderOption = document.createElement("option");
  placeholderOption.value = "";
  placeholderOption.textContent = placeholder;
  select.appendChild(placeholderOption);

  items.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.name;
    option.selected = item.id === previous;
    select.appendChild(option);
  });
}

function renderSummary() {
  const selectedEnvironment = state.environments.find((item) => item.key === state.environment);
  const selectedAgreement = getSelectedItem(state.options.agreements, state.selections.agreementId);
  const selectedProduct = getSelectedItem(state.options.products, state.selections.productId);
  const processorLabel = state.processorCode ? state.processorCode.toUpperCase() : "-";

  dom.summaryEnvironment.textContent = selectedEnvironment?.label || "-";
  dom.summaryAgreement.textContent = selectedAgreement?.name || "-";
  dom.summaryProduct.textContent = selectedProduct?.name || "-";
  dom.summaryProcessor.textContent = processorLabel;
  dom.sidebarProcessor.textContent = processorLabel;
  dom.sidebarProposalCode.textContent = state.simulation?.code || "-";
  dom.sidebarContractCode.textContent = state.proposal?.contractCode || "-";
}

function renderPreview() {
  if (!state.preview) {
    dom.previewPlaceholder.classList.remove("is-hidden");
    dom.previewCard.classList.add("is-hidden");
    dom.previewRecordControls.classList.add("is-hidden");
    return;
  }

  dom.previewPlaceholder.classList.add("is-hidden");
  dom.previewCard.classList.remove("is-hidden");
  dom.previewProcessorBadge.textContent = (state.processorCode || state.preview.processorCode || "-").toUpperCase();
  dom.previewWorksheetTitle.textContent = state.preview.worksheetName || "-";
  dom.previewBalanceValue.textContent = formatBalanceValue(state.preview.balanceValue);
  dom.previewCpfValue.textContent = state.preview.maskedCpf || state.preview.cpf || "-";
  dom.previewMatricula.textContent = state.preview.matricula || "Nao informada";
  dom.previewHelperText.textContent = buildPreviewNarrative();
  const totalRecords = Number(state.preview.matchingRecordsCount || 0);
  const hasMultipleRecords = totalRecords > 1;
  dom.previewRecordControls.classList.toggle("is-hidden", !hasMultipleRecords);
  dom.previewRecordCounter.textContent = `Registro ${state.preview.selectedRecordNumber || 1} de ${totalRecords || 1}`;
  dom.nextPreviewRecordButton.disabled = !hasMultipleRecords;
}

function buildPreviewNarrative() {
  if (isCipProcessor()) {
    return "A margem pode ser recalculada online antes da simulacao.";
  }
  if (isSerproProcessor()) {
    return "A consulta pode completar os dados de beneficio antes da simulacao.";
  }
  if (isZetraProcessor()) {
    return "A matricula da base sera usada como benefit number quando existir.";
  }
  return "A base selecionada ja esta pronta para uso.";
}

function renderAdvancedPanels() {
  const saleModality = getSelectedItem(state.options.saleModalities, state.selections.saleModalityId);
  const needsCcb = requiresOriginalCcb(saleModality?.name || "");

  dom.cipPanel.classList.toggle("is-hidden", !isCipProcessor());
  dom.zetraPanel.classList.toggle("is-hidden", !isZetraProcessor());
  dom.serproPanel.classList.toggle("is-hidden", !isSerproProcessor());
  dom.ccbPanel.classList.toggle("is-hidden", !needsCcb);

  if (!state.preview) {
    toggleNameSuggestion(false);
    dom.zetraHint.textContent = "A matricula e a senha da base serao usadas automaticamente quando existirem.";
    return;
  }

  if (state.preview.nome) {
    dom.nameSuggestionBadge.textContent = `Sugestao: ${state.preview.nome}`;
    toggleNameSuggestion(true);
  } else {
    toggleNameSuggestion(false);
  }

  if (!dom.benefitNumberInput.value && state.preview.matricula) {
    dom.benefitNumberInput.value = state.preview.matricula;
  }

  if (isZetraProcessor()) {
    if (!dom.userPasswordInput.value && state.preview.senha) {
      dom.userPasswordInput.value = state.preview.senha;
    }
    dom.zetraHint.textContent = state.preview.senha
      ? "Matricula e senha ja vieram da base. Edite apenas se precisar de fallback manual."
      : "A matricula da base sera usada automaticamente. A senha e opcional.";
  } else {
    dom.userPasswordInput.value = "";
  }

  renderProcessorZoneEmpty();
}

function renderWarnings() {
  dom.warningList.innerHTML = "";
  if (!state.warnings.length) {
    dom.warningList.classList.add("is-hidden");
    return;
  }

  dom.warningList.classList.remove("is-hidden");
  state.warnings.forEach((warning) => {
    const item = document.createElement("div");
    item.className = "warning-item";
    item.textContent = warning;
    dom.warningList.appendChild(item);
  });
}

function renderProposalWorkspace() {
  const currentBenefitNumber = dom.benefitNumberInput.value.trim() || state.preview?.matricula || "-";
  const currentDocument = sanitizeDigits(dom.clientDocumentInput.value);
  const generatedType = state.proposalGenerated?.contractDocumentType || "RG ou CNH automatico";
  const generatedEmail = state.proposalGenerated?.email || "Sera gerado na emissao";

  dom.proposalSimulationId.textContent = state.simulation?.id ? String(state.simulation.id) : "-";
  dom.proposalMainDocument.textContent = currentDocument || "-";
  dom.proposalBenefitPreview.textContent = currentBenefitNumber || "-";
  dom.proposalDocumentPreview.textContent = state.proposalGenerated?.contractDocumentMasked
    ? `${generatedType} - ${state.proposalGenerated.contractDocumentMasked}`
    : generatedType;
  dom.proposalEmailPreview.textContent = generatedEmail;
}

function renderResults() {
  renderContractResult();
  renderProposalResult();
}

function renderContractResult() {
  const selectedAgreement = getSelectedItem(state.options.agreements, state.selections.agreementId);
  const selectedEnvironment = state.environments.find((item) => item.key === state.environment);
  const hasProposal = Boolean(state.proposal);
  const hasSimulation = Boolean(state.simulation);
  const hasData = hasProposal || hasSimulation;

  dom.contractCard.classList.toggle("empty-result", !hasData);
  dom.contractCard.classList.toggle("has-result", hasData);
  dom.contractCard.classList.toggle("is-success", hasProposal);
  dom.contractCode.textContent = hasProposal
    ? state.proposal.contractCode || "Sem contrato"
    : hasSimulation ? "Aguardando proposta" : "Aguardando";
  dom.contractNarrative.textContent = hasData
    ? `${selectedEnvironment?.label || "-"} - ${selectedAgreement?.name || "Caso atual"}`
    : "O contrato aparece aqui apos a proposta.";
  dom.resultRequestedValue.textContent = hasSimulation ? formatCents(state.simulation.requestedValue) : "-";
  dom.resultInstallmentValue.textContent = hasSimulation ? formatCents(state.simulation.installmentValue) : "-";
  dom.resultDeadline.textContent = hasSimulation && state.simulation.deadline ? `${state.simulation.deadline} meses` : "-";
  dom.resultMarginValue.textContent = hasSimulation ? formatCents(state.simulation.marginValue) : "-";
}

function renderProposalResult() {
  const hasProposal = Boolean(state.proposal);
  dom.proposalCard.classList.toggle("empty-result", !hasProposal);
  dom.proposalCode.textContent = hasProposal ? state.proposal.simulationCode || "Sem codigo" : "Aguardando";
  dom.proposalNarrative.textContent = hasProposal
    ? `${state.proposal.clientName || "Cliente"} - simulacao ${state.proposal.simulationCode || "atual"}`
    : "A proposta aparece aqui depois da simulacao.";
  dom.proposalId.textContent = hasProposal ? String(state.proposal.id || "-") : "-";
  dom.proposalDocumentType.textContent = hasProposal ? state.proposalGenerated?.contractDocumentType || "-" : "-";
  dom.proposalDocumentMasked.textContent = hasProposal ? state.proposalGenerated?.contractDocumentMasked || "-" : "-";
  dom.proposalEmail.textContent = hasProposal ? state.proposalGenerated?.email || "-" : "-";
}

function renderStatusCopy() {
  const statusText = buildJourneyStatus();
  dom.sidebarStatusText.textContent = statusText;
  dom.footerStatusText.textContent = statusText;
}

function renderJourneyIndicators() {
  const statuses = {
    overviewSection: state.connected ? "complete" : "pending",
    simulationSection: resolveSimulationSectionStatus(),
    proposalSection: resolveProposalSectionStatus(),
    resultsSection: resolveResultsSectionStatus(),
    historySection: state.proposalHistory.length > 0 ? "complete" : (state.connected ? "progress" : "pending"),
    observabilitySection: resolveObservabilitySectionStatus(),
  };

  dom.navItems.forEach((item) => {
    item.classList.remove("status-pending", "status-progress", "status-complete", "status-error");
    item.classList.add(`status-${statuses[item.dataset.scrollTarget] || "pending"}`);
  });
}

function resolveSimulationSectionStatus() {
  if (state.simulationStatus === "error") {
    return "error";
  }
  if (state.simulation) {
    return "complete";
  }
  if (state.preview || hasSelectionCore()) {
    return "progress";
  }
  return state.connected ? "progress" : "pending";
}

function resolveProposalSectionStatus() {
  if (state.proposalStatus === "error") {
    return "error";
  }
  if (state.proposal) {
    return "complete";
  }
  if (state.simulation) {
    return "progress";
  }
  return "pending";
}

function resolveResultsSectionStatus() {
  if (state.proposalStatus === "error" || state.simulationStatus === "error") {
    return "error";
  }
  if (state.proposal) {
    return "complete";
  }
  if (state.simulation) {
    return "progress";
  }
  return "pending";
}

function resolveObservabilitySectionStatus() {
  if ((state.observabilitySummary?.totalExecutions || 0) > 0) {
    return "complete";
  }
  if (state.proposalHistory.length > 0 || hasActiveHistoryExecutions()) {
    return "progress";
  }
  return "pending";
}

function buildJourneyStatus() {
  if (!state.connected) {
    return "Conecte um ambiente para comecar.";
  }
  if (hasActiveHistoryExecutions()) {
    return "Executando as esteiras configuradas. Acompanhe o andamento da rodada na tela.";
  }
  if (!hasSelectionCore()) {
    return "Escolha convenio, produto, modalidade e tipo de saque.";
  }
  if (!state.preview) {
    return "Consulte a base da processadora.";
  }
  if (!isSimulationReady()) {
    return "Revise nome, telefone e ajustes do caso.";
  }
  if (!state.simulation) {
    return "Tudo pronto para gerar a simulacao.";
  }
  if (!state.proposal) {
    return "Simulacao pronta. Voce ja pode emitir a proposta.";
  }
  if ((state.observabilitySummary?.totalExecutions || 0) > 0) {
    return "Resultados da rodada prontos para analise.";
  }
  if (state.proposalHistory.length > 0) {
    return "Historico pronto. Configure e execute as esteiras para gerar resultados.";
  }
  return "Proposta emitida. Se quiser, inicie uma nova proposta ou siga para o historico.";
}

function renderConnectButton() {
  const isConnected = Boolean(state.connected);
  dom.connectButton.textContent = isConnected ? "Conectado" : "Conectar";
  dom.connectButton.classList.toggle("is-connected", isConnected);
}

function renderActionState() {
  dom.previewButton.disabled = !(state.connected && state.selections.agreementId && state.selections.productId);
  dom.simulateButton.disabled = !isSimulationReady();

  const proposalBlocked = !isProposalReady() || Boolean(state.proposal) || state.proposalCooldown;
  dom.proposalButton.disabled = proposalBlocked;

  if (state.proposalCooldown) {
    dom.proposalButton.innerHTML = `<span class="inline-block h-4 w-4 rounded-full border-2 border-slate-300 dark:border-slate-500 border-t-blue-600 animate-spin mr-2"></span>Aguardando persistencia...`;
  } else {
    dom.proposalButton.textContent = "Emitir Proposta";
  }
}

function renderProposalFeedback() {
  dom.proposalActionCard.classList.remove("is-success", "is-error");
  dom.proposalCard.classList.remove("is-success", "is-error");

  if (state.proposalStatus === "success" && state.proposal) {
    dom.proposalStatusBanner.className = "inline-status success";
    dom.proposalStatusBanner.textContent = `Proposta emitida com sucesso. Contrato ${state.proposal.contractCode || "sem codigo"}.`;
    dom.proposalActionCard.classList.add("is-success");
    dom.proposalCard.classList.add("is-success");
    return;
  }

  if (state.proposalStatus === "error") {
    dom.proposalStatusBanner.className = "inline-status error";
    dom.proposalStatusBanner.textContent = "A emissao da proposta falhou. Revise os detalhes tecnicos abaixo.";
    dom.proposalActionCard.classList.add("is-error");
    dom.proposalCard.classList.add("is-error");
    return;
  }

  if (state.proposalStatus === "running") {
    dom.proposalStatusBanner.className = "inline-status info";
    dom.proposalStatusBanner.textContent = "Emitindo a proposta...";
    return;
  }

  if (state.simulation) {
    dom.proposalStatusBanner.className = "inline-status info";
    dom.proposalStatusBanner.textContent = "Simulacao pronta. A proposta ja pode ser emitida.";
    return;
  }

  dom.proposalStatusBanner.className = "inline-status neutral";
  dom.proposalStatusBanner.textContent = "Aguardando simulacao para liberar a proposta.";
}

function renderNextProposalAction() {
  const shouldShow = state.proposalStatus === "success" && Boolean(state.proposal);
  dom.nextProposalPanel.classList.toggle("is-hidden", !shouldShow);
}

function handleEnvironmentClick(event) {
  const button = event.target.closest(".environment-btn");
  if (!button) {
    return;
  }
  const nextEnvironment = button.dataset.environment;
  if (!nextEnvironment || nextEnvironment === state.environment) {
    return;
  }
  state.environment = nextEnvironment;
  resetWorkspace({ preserveEnvironment: true });
  clearTechnicalDetails();
  setStatusBanner("Ambiente alterado. Conecte novamente para seguir.", "info");
  renderAll();
}

async function handleConnect() {
  if (!state.environment) {
    setStatusBanner("Escolha um ambiente antes de conectar.", "warning");
    return;
  }

  clearTechnicalDetails();
  clearExecutionState();
  setStatusBanner("Conectando e carregando o contexto...", "info");

  try {
    const payload = await withBusyButton(dom.connectButton, "Conectando...", () => {
      return apiRequest("/api/session/connect", {
        method: "POST",
        body: JSON.stringify({ environment: state.environment }),
      });
    });

    state.connected = true;
    state.options.agreements = payload.agreements || [];
    state.options.products = payload.products || [];
    state.options.saleModalities = payload.saleModalities || [];
    state.options.withdrawTypes = payload.withdrawTypes || [];
    state.selections = {
      agreementId: "",
      productId: "",
      saleModalityId: "",
      withdrawTypeId: "",
    };
    clearPreviewState();
    clearClientState();
    setStatusBanner("Tudo pronto para montar o caso.", "success");
  } catch (error) {
    state.connected = false;
    setStatusBanner(error.message || "Nao foi possivel conectar.", "error");
    showTechnicalDetails(error);
  }

  renderAll();

  if (state.connected) {
    scrollSectionToTop("simulationSection");
    fetchProposalHistory();
  }
}

function handleSelectionChange(event) {
  const target = event.target;

  if (target === dom.agreementSelect) {
    if (state.selections.agreementId !== target.value) {
      clearPreviewState();
    }
    state.selections.agreementId = target.value;
  }

  if (target === dom.productSelect) {
    if (state.selections.productId !== target.value) {
      clearPreviewState();
    }
    state.selections.productId = target.value;
  }

  if (target === dom.saleModalitySelect) {
    state.selections.saleModalityId = target.value;
  }

  if (target === dom.withdrawTypeSelect) {
    state.selections.withdrawTypeId = target.value;
  }

  clearExecutionState();
  clearTechnicalDetails();
  renderAll();
}

function applyPreviewRecord(record) {
  const previousPreview = state.preview;
  const previousBenefitNumber = previousPreview?.matricula || "";
  const previousUserPassword = previousPreview?.senha || "";
  const currentBenefitNumber = dom.benefitNumberInput.value.trim();
  const currentUserPassword = dom.userPasswordInput.value.trim();

  state.preview = record || null;
  dom.clientDocumentInput.value = sanitizeDigits(state.preview?.cpf || "");
  dom.documentHelper.textContent = dom.clientDocumentInput.value
    ? "CPF carregado da base."
    : "A base nao retornou CPF para este caso.";

  const nextBenefitNumber = state.preview?.matricula || "";
  const nextUserPassword = state.preview?.senha || "";
  if (!currentBenefitNumber || currentBenefitNumber === previousBenefitNumber) {
    dom.benefitNumberInput.value = nextBenefitNumber;
  }
  if (!currentUserPassword || currentUserPassword === previousUserPassword) {
    dom.userPasswordInput.value = nextUserPassword;
  }
}

async function requestPreviewRecord(sheetRecordIndex = 0, busyButton = dom.previewButton, busyLabel = "Consultando...") {
  return withBusyButton(busyButton, busyLabel, () => {
    return apiRequest("/api/session/preview", {
      method: "POST",
      body: JSON.stringify({
        environment: state.environment,
        agreementId: state.selections.agreementId,
        productId: state.selections.productId,
        sheetRecordIndex,
      }),
    });
  });
}

async function handlePreview() {
  if (!state.connected) {
    setStatusBanner("Conecte um ambiente antes de consultar a base.", "warning");
    return;
  }
  if (!state.selections.agreementId || !state.selections.productId) {
    setStatusBanner("Escolha convenio e produto para consultar a base.", "warning");
    return;
  }

  clearExecutionState();
  clearTechnicalDetails();
  setStatusBanner("Consultando a base da processadora...", "info");
  showPreviewSkeleton();

  try {
    const payload = await requestPreviewRecord(0, dom.previewButton, "Consultando...");

    state.processorCode = payload.processorCode || "";
    applyPreviewRecord(payload.record || null);

    if (state.nameMode === "faker" && !dom.clientNameInput.value) {
      await fillWithFaker("name");
    }
    if (state.phoneMode === "faker" && !dom.clientPhoneInput.value) {
      await fillWithFaker("phone");
    }
    if ((state.preview?.matchingRecordsCount || 0) > 1) {
      setStatusBanner("Base pronta. Se quiser, voce pode buscar outro registro elegivel.", "success");
    } else {
      setStatusBanner("Base pronta. Revise o caso e siga para a simulacao.", "success");
    }
  } catch (error) {
    clearPreviewState();
    setStatusBanner(error.message || "Nao foi possivel consultar a base.", "error");
    showTechnicalDetails(error);
  }

  renderAll();
}

async function handleNextPreviewRecord() {
  if (!state.preview || (state.preview.matchingRecordsCount || 0) <= 1) {
    return;
  }

  clearExecutionState();
  clearTechnicalDetails();

  const currentIndex = Number(state.preview.selectedRecordIndex || 0);
  const totalRecords = Number(state.preview.matchingRecordsCount || 0);
  const nextIndex = totalRecords > 0 ? (currentIndex + 1) % totalRecords : 0;
  const wrappedToStart = totalRecords > 0 && nextIndex === 0 && currentIndex !== 0;

  setStatusBanner("Buscando outro registro elegivel...", "info");

  try {
    const payload = await requestPreviewRecord(nextIndex, dom.nextPreviewRecordButton, "Buscando...");
    state.processorCode = payload.processorCode || state.processorCode;
    applyPreviewRecord(payload.record || null);
    setStatusBanner(
      wrappedToStart
        ? "Voltei para o primeiro registro elegivel da base."
        : "Mostrei outro registro elegivel para este caso.",
      "success"
    );
  } catch (error) {
    setStatusBanner(error.message || "Nao foi possivel buscar outro registro da base.", "error");
    showTechnicalDetails(error);
  }

  renderAll();
}

async function handleSimulate() {
  if (!isSimulationReady()) {
    setStatusBanner("Complete os dados obrigatorios antes de simular.", "warning");
    return;
  }

  clearTechnicalDetails();
  clearSimulationState();
  clearProposalState();
  state.simulationStatus = "running";
  state.proposalStatus = "idle";
  setStatusBanner("Gerando a simulacao...", "info");

  try {
    const payload = await withBusyButton(dom.simulateButton, "Simulando...", () => {
      return apiRequest("/api/session/simulate", {
        method: "POST",
        body: JSON.stringify(buildSimulationRequest()),
      });
    });

    state.processorCode = payload.processorCode || state.processorCode;
    state.warnings = payload.warnings || [];
    state.simulation = payload.summary || null;
    state.simulationRaw = payload.raw || null;
    state.simulationStatus = "success";
    state.proposalCooldown = true;
    setStatusBanner("Simulacao pronta. Aguardando persistencia dos dados...", "info");
    renderAll();
    scrollSectionToTop("proposalSection");

    window.setTimeout(() => {
      state.proposalCooldown = false;
      setStatusBanner("Simulacao pronta. A area de proposta ja foi liberada.", "success");
      renderAll();
    }, 5000);
    return;
  } catch (error) {
    state.simulationStatus = "error";
    setStatusBanner(error.message || "A simulacao nao foi concluida.", "error");
    showTechnicalDetails(error);
  }

  renderAll();
}

async function handleProposal() {
  if (state.proposalCooldown) {
    setStatusBanner("Aguarde a persistencia da simulacao antes de emitir a proposta.", "warning");
    return;
  }
  if (!isProposalReady()) {
    setStatusBanner("Gere a simulacao antes de emitir a proposta.", "warning");
    return;
  }

  clearTechnicalDetails();
  clearProposalState();
  state.proposalStatus = "running";
  setStatusBanner("Emitindo a proposta...", "info");

  try {
    const payload = await withBusyButton(dom.proposalButton, "Emitindo...", () => {
      return apiRequest("/api/session/proposal", {
        method: "POST",
        body: JSON.stringify(buildProposalRequest()),
      });
    });

    state.proposal = payload.summary || null;
    state.proposalGenerated = payload.generated || null;
    state.proposalRaw = payload.raw || null;
    state.proposalStatus = "success";

    const optimisticRecord = buildOptimisticProposalHistoryRecord(payload);
    if (optimisticRecord) {
      upsertProposalHistoryRecord(optimisticRecord);
    }

    setStatusBanner("Proposta emitida com sucesso. Se quiser, inicie uma nova proposta.", "success");
    renderAll();
    await fetchProposalHistory({ preserveCurrentOnEmpty: true });
    scrollSectionToTop("resultsSection");
    return;
  } catch (error) {
    state.proposalStatus = "error";
    setStatusBanner(error.message || "A proposta nao foi concluida.", "error");
    showTechnicalDetails(error);
  }

  renderAll();
}

function handleStartNextProposal() {
  if (!state.connected) {
    return;
  }

  clearTechnicalDetails();
  state.selections = {
    agreementId: "",
    productId: "",
    saleModalityId: "",
    withdrawTypeId: "",
  };
  clearPreviewState();
  clearClientState();
  dom.allowCipFallbackInput.checked = true;
  setStatusBanner("Tudo pronto para montar uma nova proposta neste ambiente.", "success");
  renderAll();
  scrollSectionToTop("simulationSection");
  window.setTimeout(() => {
    dom.agreementSelect?.focus();
  }, 180);
}

function buildSimulationRequest() {
  return {
    environment: state.environment,
    agreementId: state.selections.agreementId,
    productId: state.selections.productId,
    sheetRecordIndex: Number(state.preview?.selectedRecordIndex || 0),
    saleModalityId: state.selections.saleModalityId,
    withdrawTypeId: state.selections.withdrawTypeId,
    clientName: dom.clientNameInput.value.trim(),
    clientDocument: sanitizeDigits(dom.clientDocumentInput.value),
    clientPhone: sanitizeDigits(dom.clientPhoneInput.value),
    benefitNumber: dom.benefitNumberInput.value.trim(),
    userPassword: isZetraProcessor() ? dom.userPasswordInput.value.trim() : "",
    sponsorBenefitNumber: dom.sponsorBenefitNumberInput.value.trim(),
    serproAgencyId: dom.serproAgencyIdInput.value.trim(),
    serproAgencySubId: dom.serproAgencySubIdInput.value.trim(),
    serproAgencySubUpagId: dom.serproAgencySubUpagIdInput.value.trim(),
    originalCcbCode: dom.originalCcbCodeInput.value.trim(),
    originalCcbOrigin: dom.originalCcbOriginInput.value.trim(),
    allowCipFallback: Boolean(dom.allowCipFallbackInput.checked),
  };
}

function buildProposalRequest() {
  return {
    environment: state.environment,
    agreementId: state.selections.agreementId,
    clientName: dom.clientNameInput.value.trim(),
    clientDocument: sanitizeDigits(dom.clientDocumentInput.value),
    clientPhone: sanitizeDigits(dom.clientPhoneInput.value),
    benefitNumber: dom.benefitNumberInput.value.trim(),
    simulationData: state.simulationRaw?.data || null,
    processorCode: state.processorCode || "",
  };
}

async function fillWithFaker(kind) {
  const button = kind === "name" ? dom.generateNameButton : dom.generatePhoneButton;
  const input = kind === "name" ? dom.clientNameInput : dom.clientPhoneInput;

  try {
    const payload = await withBusyButton(button, "Gerando...", () => {
      return apiRequest(`/api/faker?kind=${encodeURIComponent(kind)}`);
    });
    input.value = payload.value || "";
    clearExecutionState();
    setStatusBanner(kind === "name" ? "Nome ficticio gerado." : "Telefone ficticio gerado.", "info");
  } catch (error) {
    setStatusBanner(error.message || "Nao foi possivel gerar o dado ficticio.", "error");
    showTechnicalDetails(error);
  }

  renderWarnings();
  renderResults();
  renderProposalWorkspace();
  renderProposalFeedback();
  renderNextProposalAction();
  renderActionState();
  renderStatusCopy();
  renderJourneyIndicators();
}

function updateModeButtons(kind, mode) {
  const selector = kind === "name" ? "[data-name-mode]" : "[data-phone-mode]";
  document.querySelectorAll(selector).forEach((button) => {
    const buttonMode = kind === "name" ? button.dataset.nameMode : button.dataset.phoneMode;
    const isActive = buttonMode === mode;
    button.classList.toggle("is-active", isActive);
    button.classList.toggle("active", isActive);
  });
}

function toggleNameSuggestion(show) {
  dom.nameSuggestionBadge.classList.toggle("is-hidden", !show);
  dom.useSuggestedNameButton.classList.toggle("is-hidden", !show);
}

function hasSelectionCore() {
  return Boolean(
    state.selections.agreementId &&
      state.selections.productId &&
      state.selections.saleModalityId &&
      state.selections.withdrawTypeId
  );
}

function isSimulationReady() {
  if (!state.connected || !hasSelectionCore() || !state.preview) {
    return false;
  }

  const hasClientName = Boolean(dom.clientNameInput.value.trim());
  const hasClientDocument = Boolean(sanitizeDigits(dom.clientDocumentInput.value));
  const hasClientPhone = Boolean(sanitizeDigits(dom.clientPhoneInput.value));

  if (!hasClientName || !hasClientDocument || !hasClientPhone) {
    return false;
  }

  if (isZetraProcessor() && !dom.benefitNumberInput.value.trim() && !state.preview?.matricula) {
    return false;
  }

  if (requiresOriginalCcb(getSelectedItem(state.options.saleModalities, state.selections.saleModalityId)?.name || "")) {
    if (!dom.originalCcbCodeInput.value.trim() || !dom.originalCcbOriginInput.value.trim()) {
      return false;
    }
  }

  return true;
}

function isProposalReady() {
  return Boolean(state.simulationRaw?.data?.id);
}

function getSelectedItem(items, itemId) {
  return items.find((item) => item.id === itemId) || null;
}

function requiresOriginalCcb(saleModalityName) {
  const normalized = String(saleModalityName || "").trim().toLowerCase();
  return normalized.includes("agrega") || normalized.includes("refin");
}

function isCipProcessor() {
  return normalizeProcessorCode(state.processorCode) === "cip";
}

function isSerproProcessor() {
  return normalizeProcessorCode(state.processorCode) === "serpro";
}

function isZetraProcessor() {
  const normalized = normalizeProcessorCode(state.processorCode);
  return normalized === "zetra" || normalized === "econsig-zetra";
}

function normalizeProcessorCode(processorCode) {
  return String(processorCode || "").trim().toLowerCase();
}

function setStatusBanner(message, tone = "neutral") {
  dom.statusBanner.textContent = message;
  dom.statusBanner.className = `status-banner ${tone}`;
  renderStatusCopy();
}

function clearExecutionState() {
  clearSimulationState();
  clearProposalState();
  state.simulationStatus = "idle";
  state.proposalStatus = "idle";
  state.warnings = [];
}

function clearSimulationState() {
  state.simulation = null;
  state.simulationRaw = null;
}

function clearProposalState() {
  state.proposal = null;
  state.proposalRaw = null;
  state.proposalGenerated = null;
  state.proposalCooldown = false;
}

function clearPreviewState() {
  state.preview = null;
  state.processorCode = "";
  clearExecutionState();
  dom.clientDocumentInput.value = "";
  dom.documentHelper.textContent = "O CPF sera preenchido pela base quando existir.";
  dom.benefitNumberInput.value = "";
  dom.userPasswordInput.value = "";
  dom.serproAgencyIdInput.value = "";
  dom.serproAgencySubIdInput.value = "";
  dom.serproAgencySubUpagIdInput.value = "";
  dom.sponsorBenefitNumberInput.value = "";
  dom.originalCcbCodeInput.value = "";
  dom.originalCcbOriginInput.value = "";
  toggleNameSuggestion(false);
}

function clearClientState() {
  dom.clientNameInput.value = "";
  dom.clientDocumentInput.value = "";
  dom.clientPhoneInput.value = "";
  dom.documentHelper.textContent = "O CPF sera preenchido pela base quando existir.";
  state.nameMode = "manual";
  state.phoneMode = "manual";
  updateModeButtons("name", state.nameMode);
  updateModeButtons("phone", state.phoneMode);
  toggleNameSuggestion(false);
}

function resetWorkspace({ preserveEnvironment } = { preserveEnvironment: true }) {
  if (!preserveEnvironment) {
    state.environment = "";
  }

  state.connected = false;
  state.options = {
    agreements: [],
    products: [],
    saleModalities: [],
    withdrawTypes: [],
  };
  state.selections = {
    agreementId: "",
    productId: "",
    saleModalityId: "",
    withdrawTypeId: "",
  };
  state.proposalHistory = [];
  state.observabilitySummary = buildEmptyObservabilitySummary();
  state.flowConfigs = {};
  state.expandedFlowRows = {};
  state.loadingHistoryFlows = {};
  state.historyFlowErrors = {};
  state.executingHistoryRows = {};
  state.batchCancelled = false;
  state.batchExecutionActive = false;
  clearPreviewState();
  clearClientState();
  dom.allowCipFallbackInput.checked = true;
}

function clearTechnicalDetails() {
  dom.errorDetails.classList.add("is-hidden");
  dom.errorDetails.open = false;
  dom.errorDetailText.textContent = "";
}

function showTechnicalDetails(error) {
  const detail = error?.detail || error?.message || "Sem detalhes tecnicos disponiveis.";
  dom.errorDetails.classList.remove("is-hidden");
  dom.errorDetailText.textContent = detail;
  scrollSectionToTop("resultsSection");
}

function restoreSidebarState() {
  const collapsed = localStorage.getItem("suite-consignado-sidebar-collapsed") === "true";
  setSidebarCollapsed(collapsed);
}

function toggleSidebar() {
  if (window.innerWidth <= 980) {
    document.body.classList.toggle("sidebar-open");
  } else {
    setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
  }
}

function closeMobileSidebar() {
  document.body.classList.remove("sidebar-open");
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", Boolean(collapsed));
  localStorage.setItem("suite-consignado-sidebar-collapsed", String(Boolean(collapsed)));
}

function scrollSectionToTop(sectionId, { behavior = "smooth" } = {}) {
  const section = document.getElementById(sectionId);
  const container = dom.appContent;
  if (!section || !container) {
    return;
  }

  const target = section.firstElementChild instanceof HTMLElement ? section.firstElementChild : section;
  const containerRect = container.getBoundingClientRect();
  const targetRect = target.getBoundingClientRect();
  const paddingTop = Number.parseFloat(window.getComputedStyle(container).paddingTop || "0") || 0;
  const top = container.scrollTop + (targetRect.top - containerRect.top) - Math.max(4, paddingTop - 4);

  container.scrollTo({
    top: Math.max(0, top),
    behavior,
  });
  setActiveNav(sectionId);
}

function setupSectionObserver() {
  if (!("IntersectionObserver" in window)) {
    return;
  }
  sectionObserver = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible?.target?.id) {
        setActiveNav(visible.target.id);
      }
    },
    {
      root: dom.appContent,
      threshold: [0.25, 0.55, 0.8],
    }
  );

  dom.pageSections.forEach((section) => sectionObserver.observe(section));
}

function setupLayoutSync() {
  syncSidebarBrandHeight();

  if ("ResizeObserver" in window && dom.appHeader) {
    headerResizeObserver = new ResizeObserver(() => {
      syncSidebarBrandHeight();
    });
    headerResizeObserver.observe(dom.appHeader);
  }

  window.addEventListener("resize", () => {
    syncSidebarBrandHeight();
    if (window.innerWidth > 980) {
      closeMobileSidebar();
    }
  });
}

function syncSidebarBrandHeight() {
  if (!dom.sidebarBrandTop || !dom.appHeader) {
    return;
  }

  const headerHeight = Math.ceil(dom.appHeader.getBoundingClientRect().height);
  if (headerHeight > 0) {
    dom.sidebarBrandTop.style.height = `${headerHeight}px`;
  }
}

function setActiveNav(sectionId) {
  dom.navItems.forEach((item) => {
    const isActive = item.dataset.scrollTarget === sectionId;
    item.classList.toggle("active", isActive);
  });
}

async function withBusyButton(button, busyLabel, callback) {
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = busyLabel;
  button.classList.add("is-loading");
  try {
    return await callback();
  } finally {
    button.disabled = false;
    button.textContent = originalText;
    button.classList.remove("is-loading");
  }
}

async function apiRequest(url, options = {}) {
  const requestOptions = {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  };

  const response = await fetch(url, requestOptions);
  const rawText = await response.text();
  let payload = {};

  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch (error) {
      payload = {};
    }
  }

  if (!response.ok || payload.error) {
    const apiError = payload.error || {};
    const error = new Error(apiError.message || `Falha na requisicao (${response.status})`);
    error.status = response.status;
    error.code = apiError.code || "request_failed";
    error.detail = apiError.detail || rawText;
    throw error;
  }

  return payload;
}

function applyStoredTheme() {
  const storedTheme = localStorage.getItem("suite-consignado-theme") || "light";
  applyTheme(storedTheme);
}

function applyTheme(theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("suite-consignado-theme", theme);
  document.querySelectorAll("[data-theme-value]").forEach((button) => {
    const isActive = button.dataset.themeValue === theme;
    button.classList.toggle("is-active", isActive);
    button.classList.toggle("active", isActive);
  });
}

function formatBalanceValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const text = String(value).trim();
  if (text.startsWith("R$")) {
    return text;
  }
  const normalized = text.replace("R$", "").replace(/\./g, "").replace(",", ".").trim();
  const numeric = Number(normalized);
  if (Number.isFinite(numeric)) {
    return new Intl.NumberFormat("pt-BR", {
      style: "currency",
      currency: "BRL",
    }).format(numeric);
  }
  return text;
}

function formatCents(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return String(value);
  }
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(numeric / 100);
}

function sanitizeDigits(value) {
  return String(value || "").replace(/\D+/g, "");
}

function maskDigits(value) {
  const digits = sanitizeDigits(value);
  if (!digits) {
    return "-";
  }
  if (digits.length <= 4) {
    return digits;
  }
  return `${"*".repeat(digits.length - 4)}${digits.slice(-4)}`;
}

// ==========================================================================
// HISTORICO DE PROPOSTAS
// ==========================================================================

function renderHistory() {
  const records = state.proposalHistory;
  const hasRecords = records.length > 0;

  dom.historyEmptyState.classList.toggle("is-hidden", hasRecords);
  dom.historyTableWrapper.classList.toggle("is-hidden", !hasRecords);
  dom.historyBatchAction.classList.toggle("is-hidden", records.length < 2);

  if (!hasRecords) {
    dom.historyTableBody.innerHTML = "";
    return;
  }

  const rows = records.map((record) => {
    const agreementName = resolveOptionName(state.options.agreements, record.agreementId) || record.agreementId;
    const productName = resolveOptionName(state.options.products, record.productId) || record.productId;
    const modalityName = resolveOptionName(state.options.saleModalities, record.saleModalityId) || record.saleModalityId;
    const withdrawName = resolveOptionName(state.options.withdrawTypes, record.withdrawTypeId) || record.withdrawTypeId;
    const processorLabel = (record.processorCode || "-").toUpperCase();
    const cpfDisplay = formatCpf(record.clientDocument);
    const isExpanded = Boolean(state.expandedFlowRows[record.index]);
    const isLoadingFlow = Boolean(state.loadingHistoryFlows[record.index]);
    const flowErrorMessage = state.historyFlowErrors[record.index] || "";
    const isExecuting = Boolean(state.executingHistoryRows[record.index]);

    return `
      <tr class="border-b border-slate-100 dark:border-slate-800 even:bg-slate-50 dark:even:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors">
        <td class="px-4 py-3 font-mono text-xs text-slate-400">${record.index}</td>
        <td class="px-4 py-3 font-mono text-xs font-bold text-slate-900 dark:text-white">
          <div class="flex items-center gap-2">
            <button
              type="button"
              class="history-expand-btn inline-flex h-7 w-7 items-center justify-center rounded border border-slate-200 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:border-slate-700 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white transition-all ${isExpanded ? "bg-slate-100 dark:bg-slate-800" : "bg-white dark:bg-slate-900"}"
              data-action="toggle-flow"
              data-index="${record.index}"
              aria-label="${isExpanded ? "Fechar esteira" : "Abrir esteira"}"
              aria-expanded="${isExpanded ? "true" : "false"}"
              title="${isExpanded ? "Ocultar esteira" : "Mostrar esteira"}"
            >
              <svg class="h-3.5 w-3.5 transition-transform duration-200 ${isExpanded ? "rotate-90" : "rotate-0"}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M9 5l7 7-7 7"></path>
              </svg>
            </button>
            <span>${record.simulationCode || "-"}</span>
          </div>
        </td>
        <td class="px-4 py-3 text-xs text-slate-700 dark:text-slate-300">${agreementName}</td>
        <td class="px-4 py-3"><span class="inline-block px-2 py-0.5 rounded text-[0.65rem] font-bold uppercase tracking-wide bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200">${processorLabel}</span></td>
        <td class="px-4 py-3 font-mono text-xs text-slate-700 dark:text-slate-300">${record.contractCode || "-"}</td>
        <td class="px-4 py-3 font-mono text-xs text-slate-500">${cpfDisplay}</td>
        <td class="px-4 py-3 text-xs text-slate-700 dark:text-slate-300">${productName}</td>
        <td class="px-4 py-3 text-xs text-slate-700 dark:text-slate-300">${modalityName}</td>
        <td class="px-4 py-3 text-xs text-slate-700 dark:text-slate-300">${withdrawName}</td>
        <td class="px-4 py-3 text-center whitespace-nowrap">
            <button type="button" class="history-action-btn inline-flex h-8 w-8 items-center justify-center rounded border border-slate-300 dark:border-slate-600 text-slate-500 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors mr-1 ${isExecuting ? "opacity-60 cursor-not-allowed" : ""}" data-action="edit" data-index="${record.index}" title="Configurar teste" aria-label="Configurar teste" ${isExecuting ? "disabled" : ""}>
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.232 5.232l3.536 3.536M9 11l6.232-6.232a2.5 2.5 0 113.536 3.536L12.536 14.536A4 4 0 0110.5 15.5H7.5V12.5A4 4 0 018.464 10.464z"></path>
              </svg>
            </button>
            ${isExecuting ? `
            <button type="button" class="history-action-btn inline-flex h-8 w-8 items-center justify-center rounded border border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors mr-1" data-action="cancel" data-index="${record.index}" title="Cancelar execucao" aria-label="Cancelar execucao">
              <svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"></path>
              </svg>
            </button>
            <button type="button" class="history-action-btn inline-flex h-8 w-8 items-center justify-center rounded border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 opacity-80 cursor-wait" data-action="execute" data-index="${record.index}" title="Executando teste" aria-label="Executando teste" disabled>
              <span class="inline-block h-3.5 w-3.5 rounded-full border-2 border-blue-300 border-t-blue-600 animate-spin"></span>
            </button>
            ` : `
            <button type="button" class="history-action-btn inline-flex h-8 w-8 items-center justify-center rounded border border-blue-300 dark:border-blue-700 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors" data-action="execute" data-index="${record.index}" title="Executar teste" aria-label="Executar teste">
              <svg class="h-3.5 w-3.5" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 6.82v10.36c0 .79.87 1.27 1.54.84l8.14-5.18a1 1 0 000-1.68L9.54 5.98A1 1 0 008 6.82z"></path>
              </svg>
            </button>
            `}
          </td>
      </tr>
      ${isExpanded ? `
        <tr class="history-flow-detail-row border-b border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/40">
          <td colspan="10" class="px-4 py-0">
            ${buildHistoryFlowRowContent(record, {
              isLoading: isLoadingFlow,
              errorMessage: flowErrorMessage,
            })}
          </td>
        </tr>
      ` : ""}
    `;
  });

  dom.historyTableBody.innerHTML = rows.join("");

  dom.historyTableBody.querySelectorAll(".history-action-btn, .history-expand-btn").forEach((btn) => {
    btn.addEventListener("click", handleHistoryAction);
  });
}

function buildHistoryFlowRowContent(record, { isLoading, errorMessage }) {
  if (isLoading) {
    return `
      <div class="py-5 flex items-center justify-center gap-3 text-sm text-slate-500 dark:text-slate-400">
        <span class="inline-block h-5 w-5 rounded-full border-2 border-slate-300 dark:border-slate-600 border-t-blue-600 animate-spin"></span>
        <span>Consultando a esteira desta proposta...</span>
      </div>
    `;
  }

  if (errorMessage) {
    return `
      <div class="py-4">
        <div class="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700 dark:border-amber-800/40 dark:bg-amber-950/20 dark:text-amber-300">
          ${errorMessage}
        </div>
      </div>
    `;
  }

  const flow = record.flow;
  if (!flow || !Array.isArray(flow.stages) || !flow.stages.length) {
    return `
      <div class="py-4">
        <div class="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          A esteira desta proposta ainda nao esta disponivel.
        </div>
      </div>
    `;
  }

  const externalValidationFailedStageKeys = collectExternalValidationFailedStageKeys(record);
  const stagesHtml = flow.stages
    .map((stage, index) => {
      const stageIdKey = String(stage?.id || "").trim();
      const stageCodeKey = `code:${String(stage?.code || "").trim().toLowerCase()}`;
      const forceDanger =
        externalValidationFailedStageKeys.has(stageIdKey)
        || externalValidationFailedStageKeys.has(stageCodeKey);
      return buildHistoryFlowStage(stage, index === flow.stages.length - 1, {
        forceTone: forceDanger ? "danger" : "",
      });
    })
    .join("");

  return `
    <div class="py-3">
      <div class="overflow-x-auto pb-1">
        <div class="min-w-max px-2">
          <div class="flex items-start gap-0">
            ${stagesHtml}
          </div>
        </div>
      </div>
    </div>
  `;
}

function collectExternalValidationFailedStageKeys(record) {
  const failed = new Set();
  const latestExecution = record?.latestExecution || null;
  const stageResults = Array.isArray(latestExecution?.stageResults) ? latestExecution.stageResults : [];

  stageResults.forEach((stage) => {
    const finalStatus = String(stage?.finalStatus || "").toLowerCase();
    const message = String(stage?.message || "").toLowerCase();
    const hasExternalValidationFailure =
      finalStatus.includes("external_validation_failed")
      || message.includes("falha de validacao externa")
      || message.includes("external validation");

    if (!hasExternalValidationFailure) {
      return;
    }

    const stageId = String(stage?.stageId || "").trim();
    const stageCode = String(stage?.stageCode || "").trim().toLowerCase();
    if (stageId) {
      failed.add(stageId);
    }
    if (stageCode) {
      failed.add(`code:${stageCode}`);
    }
  });

  return failed;
}

function buildHistoryFlowStage(stage, isLast, { forceTone = "" } = {}) {
  const baseVisual = getHistoryFlowStageVisual(stage.status);
  const forcedVisual = forceTone ? getHistoryFlowStageVisual(forceTone) : null;
  const nodeBorderClass = forcedVisual ? forcedVisual.nodeBorderClass : baseVisual.nodeBorderClass;
  const dotClass = forcedVisual ? forcedVisual.dotClass : baseVisual.dotClass;
  const lineClass = baseVisual.lineClass;
  const stageTone = forceTone || "";
  const stageHighlightClass = stageTone === "danger"
    ? "rounded-md bg-rose-50/60 dark:bg-rose-900/15 ring-1 ring-rose-200/80 dark:ring-rose-800/40"
    : "";
  const stageLabelClass = stageTone === "danger"
    ? "text-rose-700 dark:text-rose-300"
    : "text-slate-600 dark:text-slate-300";
  const safeName = stage.name || "Etapa";
  const safeStatus = formatHistoryFlowStatus(stage.status);

  return `
    <div class="relative min-w-[150px] max-w-[150px] px-1 ${stageHighlightClass}" title="${safeName} - ${safeStatus}">
      <div class="relative h-5 mb-3">
        ${isLast ? "" : `<span class="absolute h-0.5 rounded-full ${lineClass}" style="left: calc(50% + 14px); right: -50%; top: 50%; transform: translateY(-50%);"></span>`}
        <div class="history-flow-node absolute h-5 w-5 rounded-full border-2 ${nodeBorderClass} bg-white dark:bg-slate-950 flex items-center justify-center z-10" style="left: 50%; top: 50%; transform: translate(-50%, -50%);">
          <span class="h-2 w-2 rounded-full ${dotClass}"></span>
        </div>
      </div>
      <div class="px-1 text-center">
        <span class="block text-[0.72rem] leading-tight font-medium ${stageLabelClass}">${safeName}</span>
      </div>
    </div>
  `;
}

function getHistoryFlowStageVisual(status) {
  const tone = getHistoryFlowTone(status);
  const palette = {
    neutral: {
      dotClass: "bg-slate-300 dark:bg-slate-600",
      nodeBorderClass: "border-slate-300 dark:border-slate-600",
      lineClass: "bg-slate-200 dark:bg-slate-800",
    },
    progress: {
      dotClass: "bg-blue-500",
      nodeBorderClass: "border-blue-500/90 dark:border-blue-400",
      lineClass: "bg-blue-200 dark:bg-blue-900/70",
    },
    warning: {
      dotClass: "bg-amber-500",
      nodeBorderClass: "border-amber-500/90 dark:border-amber-400",
      lineClass: "bg-amber-200 dark:bg-amber-900/70",
    },
    success: {
      dotClass: "bg-emerald-500",
      nodeBorderClass: "border-emerald-500/90 dark:border-emerald-400",
      lineClass: "bg-emerald-200 dark:bg-emerald-900/70",
    },
    danger: {
      dotClass: "bg-rose-500",
      nodeBorderClass: "border-rose-500/90 dark:border-rose-400",
      lineClass: "bg-rose-200 dark:bg-rose-900/70",
    },
  };

  return palette[tone] || palette.neutral;
}

function getHistoryFlowTone(status) {
  const normalized = String(status || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

  if (!normalized) return "neutral";
  if (/(fail|falh|erro|error|reject|reprov|cancel|canceled|cancelled|denied|invalid|expir|block|bloque|stop|failed|not_found)/.test(normalized)) return "danger";
  if (/(manual_analysis|manual analysis|analise_manual|analise manual|pendencia|pendency|alert|warn|review|attention|manual)/.test(normalized)) return "warning";
  if (/(in_progress|in progress|processing|processando|running|started|start)/.test(normalized)) return "progress";
  if (/(finaliz|sucesso|success|done|ok|completed|complete|approved|aprov|conclu|finished|finish|emitid|paid|pago|validated)/.test(normalized)) return "success";
  if (/(pending|aguard|wait|waiting|queue|queued|open|novo|nao iniciad|created|inicial|not_started)/.test(normalized)) return "neutral";
  return "neutral";
}

function formatHistoryFlowStatus(status) {
  const text = String(status || "").trim();
  return text || "Sem status";
}

async function handleHistoryAction(event) {
  const btn = event.currentTarget;
  const action = btn.dataset.action;
  const index = Number(btn.dataset.index);

  if (action === "toggle-flow") {
    await toggleHistoryFlow(index);
    return;
  }

  if (action === "edit") {
    openFlowModal(index);
  } else if (action === "execute") {
    await executeHistoryFlow(index);
  } else if (action === "cancel") {
    await cancelHistoryFlow(index);
  }
}

async function toggleHistoryFlow(index) {
  const record = state.proposalHistory.find((item) => item.index === index);
  if (!record) {
    setStatusBanner("Nao foi possivel localizar a proposta selecionada.", "warning");
    return;
  }

  if (state.expandedFlowRows[index]) {
    delete state.expandedFlowRows[index];
    delete state.loadingHistoryFlows[index];
    delete state.historyFlowErrors[index];
    renderHistory();
    return;
  }

  state.expandedFlowRows[index] = true;
  delete state.historyFlowErrors[index];

  state.loadingHistoryFlows[index] = true;
  renderHistory();

  try {
    const flow = await ensureProposalFlow(index, true);
    if (!flow || !Array.isArray(flow.stages) || !flow.stages.length) {
      throw new Error("O dashboard ainda nao retornou etapas para esta proposta.");
    }
  } catch (error) {
    state.historyFlowErrors[index] = error?.detail || error?.message || "Nao consegui carregar a esteira desta proposta agora.";
  } finally {
    delete state.loadingHistoryFlows[index];
    renderHistory();
  }
}

async function executeHistoryFlow(index) {
  let executionStarted = false;
  const record = state.proposalHistory.find((item) => item.index === index);
  if (!record) {
    setStatusBanner("Nao foi possivel localizar a proposta selecionada.", "warning");
    return;
  }

  if (state.executingHistoryRows[index]) {
    return;
  }

  clearTechnicalDetails();
  closeExecutionFinishedModal();
  state.expandedFlowRows[index] = true;
  delete state.historyFlowErrors[index];
  state.executingHistoryRows[index] = true;
  renderHistory();

  try {
    let flow = record.flow;
    if (!flow || !Array.isArray(flow.stages) || !flow.stages.length) {
      state.loadingHistoryFlows[index] = true;
      renderHistory();
      flow = await ensureProposalFlow(index, true);
    }

    if (!flow || !Array.isArray(flow.stages) || !flow.stages.length) {
      throw new Error("O dashboard ainda nao retornou etapas para esta proposta.");
    }

    delete state.loadingHistoryFlows[index];
    renderHistory();

    const latestRecord = state.proposalHistory.find((item) => item.index === index) || record;
    const executionConfig = getSavedFlowConfig(latestRecord, flow) || buildFlowConfigSnapshot(latestRecord, flow, {});

    const startPayload = await apiRequest("/api/proposal-history/execute", {
      method: "POST",
      body: JSON.stringify({
        environment: state.environment,
        historyIndex: index,
        flowConfig: executionConfig,
      }),
    });

    applyExecutionPayload(index, startPayload, latestRecord, flow, executionConfig);
    executionStarted = true;
    setStatusBanner(startPayload?.execution?.message || "Execucao iniciada. Acompanhando a esteira da proposta...", "info");

    while (state.executingHistoryRows[index]) {
      await waitForExecutionPollInterval();

      const statusPayload = await apiRequest("/api/proposal-history/execution-status", {
        method: "POST",
        body: JSON.stringify({
          environment: state.environment,
          historyIndex: index,
        }),
      });

      const execution = applyExecutionPayload(index, statusPayload, latestRecord, flow, executionConfig);
      const status = String(execution?.status || "").toLowerCase();

      if (status !== "running") {
        if (status === "completed") {
          setStatusBanner(execution.message || "Execucao da proposta finalizada. Revise a esteira para analisar o resultado.", "info");
        } else if (status === "cancelled") {
          setStatusBanner(execution.message || "Execucao da proposta cancelada.", "warning");
        } else if (status === "failed") {
          setStatusBanner(execution.message || "A execucao da proposta encontrou uma falha.", "error");
        } else {
          setStatusBanner(execution.message || "A execucao da proposta foi pausada para acompanhamento.", "warning");
        }
        await fetchProposalHistory({ preserveCurrentOnEmpty: true });
        break;
      }
    }
  } catch (error) {
    setStatusBanner(error?.message || "Nao foi possivel executar o fluxo da proposta agora.", "error");
    showTechnicalDetails(error);
  } finally {
    delete state.executingHistoryRows[index];
    delete state.loadingHistoryFlows[index];
    if (executionStarted) {
      await fetchProposalHistory({ preserveCurrentOnEmpty: true });
      maybeShowExecutionFinishedModal();
    } else {
      renderHistory();
      renderObservability();
    }
  }
}

function applyExecutionPayload(index, payload, fallbackRecord, fallbackFlow, fallbackConfig) {
  const targetRecord = state.proposalHistory.find((item) => item.index === index) || fallbackRecord || null;
  const resolvedFlow = payload?.flow || fallbackFlow || null;
  if (targetRecord && resolvedFlow) {
    targetRecord.flow = resolvedFlow;
  }

  const resolvedConfig = payload?.flowConfig || fallbackConfig || null;
  if (targetRecord && resolvedFlow && resolvedConfig) {
    state.flowConfigs[getFlowConfigKey(targetRecord, resolvedFlow)] = resolvedConfig;
  }

  renderHistory();
  return payload?.execution || {};
}

function waitForExecutionPollInterval() {
  return new Promise((resolve) => {
    window.setTimeout(resolve, EXECUTION_STATUS_POLL_INTERVAL_MS);
  });
}

function hasActiveHistoryExecutions() {
  return Object.keys(state.executingHistoryRows || {}).length > 0;
}

function showExecutionFinishedModal({
  title = "Rodada finalizada",
  message = "A rodada atual de execucoes foi finalizada. Revise os status das esteiras para analisar os resultados.",
} = {}) {
  if (!dom.executionFinishedModal) {
    return;
  }

  dom.executionFinishedModalTitle.textContent = title;
  dom.executionFinishedModalMessage.textContent = message;
  dom.executionFinishedModal.classList.remove("is-hidden");
}

function closeExecutionFinishedModal() {
  dom.executionFinishedModal?.classList.add("is-hidden");
}

function maybeShowExecutionFinishedModal() {
  if (state.batchExecutionActive || hasActiveHistoryExecutions()) {
    return;
  }

  showExecutionFinishedModal();
}

async function handleTestAll() {
  if (!state.proposalHistory || state.proposalHistory.length < 2) {
    return;
  }

  closeExecutionFinishedModal();
  state.batchCancelled = false;
  state.batchExecutionActive = true;
  const indices = state.proposalHistory.map((r) => r.index);
  const total = indices.length;
  let completed = 0;
  let failed = 0;
  let startedAny = false;

  try {
    setStatusBanner(`Execucao em lote iniciada: 0/${total} propostas processadas.`, "info");

    for (const index of indices) {
      if (state.batchCancelled) {
        setStatusBanner(`Execucao em lote cancelada: ${completed}/${total} processadas antes do cancelamento.`, "warning");
        return;
      }

      if (state.executingHistoryRows[index]) {
        continue;
      }

      try {
        startedAny = true;
        await executeHistoryFlow(index);
      } catch (_) {
        failed++;
      }

      completed++;
      const remaining = total - completed;
      if (remaining > 0 && !state.batchCancelled) {
        setStatusBanner(`Execucao em lote: ${completed}/${total} processadas, ${remaining} restante(s)...`, "info");
      }
    }

    if (state.batchCancelled) {
      setStatusBanner(`Execucao em lote cancelada: ${completed}/${total} processadas antes do cancelamento.`, "warning");
    } else if (failed > 0) {
      setStatusBanner(`Execucao em lote finalizada: ${completed}/${total} processadas, ${failed} com falha.`, "warning");
    } else {
      setStatusBanner(`Execucao em lote finalizada: ${completed}/${total} propostas processadas.`, "info");
    }
  } finally {
    state.batchExecutionActive = false;
    if ((startedAny || completed > 0) && !hasActiveHistoryExecutions()) {
      showExecutionFinishedModal();
    }
  }
}

async function cancelHistoryFlow(index) {
  try {
    await apiRequest("/api/proposal-history/cancel-execution", {
      method: "POST",
      body: JSON.stringify({
        environment: state.environment,
        historyIndex: index,
      }),
    });
    setStatusBanner(`Cancelamento solicitado para proposta #${index}.`, "warning");
  } catch (error) {
    setStatusBanner(error?.message || "Nao foi possivel cancelar a execucao.", "error");
  }
}

async function cancelAllExecutions() {
  try {
    await apiRequest("/api/proposal-history/cancel-all-executions", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setStatusBanner("Cancelamento solicitado para todas as execucoes.", "warning");
    state.batchCancelled = true;
  } catch (error) {
    setStatusBanner(error?.message || "Nao foi possivel cancelar as execucoes.", "error");
  }
}

async function resetAllExecutions() {
  try {
    await apiRequest("/api/proposal-history/reset-all-executions", {
      method: "POST",
      body: JSON.stringify({}),
    });
    Object.keys(state.executingHistoryRows).forEach((k) => delete state.executingHistoryRows[k]);
    state.batchCancelled = false;
    setStatusBanner("Todas as execucoes foram resetadas. O historico foi preservado.", "success");
    renderHistory();
  } catch (error) {
    setStatusBanner(error?.message || "Nao foi possivel resetar as execucoes.", "error");
  }
}
async function handleGenerateReport() {
  if (!state.environment) {
    setStatusBanner("Conecte um ambiente antes de gerar o relatorio.", "warning");
    return;
  }

  const hasObservabilityData = state.proposalHistory.some((record) => Array.isArray(record.executions) && record.executions.length > 0);
  if (!hasObservabilityData) {
    setStatusBanner("Ainda nao ha execucoes suficientes para gerar o relatorio.", "warning");
    return;
  }

  clearTechnicalDetails();
  setStatusBanner("Gerando relatorio da rodada atual...", "info");

  try {
    const payload = await withBusyButton(dom.generateReportButton, "Gerando...", () => {
      return apiRequest("/api/report/generate", {
        method: "POST",
        body: JSON.stringify({ environment: state.environment }),
      });
    });

    const htmlContent = String(payload?.html || "");
    if (!htmlContent) {
      throw new Error("A API nao retornou o HTML do relatorio.");
    }

    const blob = new Blob([htmlContent], { type: "text/html;charset=utf-8" });
    const reportUrl = URL.createObjectURL(blob);
    const reportWindow = window.open(reportUrl, "_blank", "noopener,noreferrer");

    if (!reportWindow) {
      URL.revokeObjectURL(reportUrl);
      throw new Error("O navegador bloqueou a abertura do relatorio em nova aba.");
    }

    window.setTimeout(() => URL.revokeObjectURL(reportUrl), 60000);

    const fileName = payload?.fileName || "relatorio-execucao.html";
    setStatusBanner(`Relatorio gerado com sucesso: ${fileName}.`, "success");
  } catch (error) {
    setStatusBanner(error?.message || "Nao foi possivel gerar o relatorio agora.", "error");
    showTechnicalDetails(error);
  }
}


function renderObservability() {
  if (!dom.observabilitySummaryStrip || !dom.observabilityProposalList || !dom.observabilityEmptyState) {
    return;
  }

  const s = { ...buildEmptyObservabilitySummary(), ...(state.observabilitySummary || {}) };
  const pending = Number(s.manualExecutions || 0) + Number(s.waitingExecutions || 0);

  const stats = [
    { label: "Propostas", value: s.proposalsWithExecutions, tone: "" },
    { label: "Execucoes", value: s.totalExecutions, tone: "tone-progress" },
    { label: "Concluidas", value: s.completedExecutions, tone: "tone-success" },
    { label: "Pendentes", value: pending, tone: pending > 0 ? "tone-warning" : "" },
    { label: "Falhas", value: s.failedExecutions, tone: s.failedExecutions > 0 ? "tone-danger" : "" },
    { label: "HTTP", value: s.totalHttpCalls, tone: "" },
    { label: "DB", value: s.totalDbChecks, tone: "" },
    { label: "Media", value: formatDurationMs(s.averageDurationMs), tone: "" },
  ];

  dom.observabilitySummaryStrip.innerHTML = stats.map((st) => `
    <div class="obs-stat">
      <span class="obs-stat-value ${st.tone}">${escapeHtml(String(st.value))}</span>
      <span class="obs-stat-label">${escapeHtml(st.label)}</span>
    </div>
  `).join("");

  const proposals = state.proposalHistory.filter((r) => Array.isArray(r.executions) && r.executions.length > 0);
  const hasObservabilityData = proposals.length > 0;
  dom.observabilityEmptyState.classList.toggle("is-hidden", hasObservabilityData);
  dom.observabilityProposalList.innerHTML = proposals.map((r) => buildObsProposalRow(r)).join("");

  if (dom.generateReportButton) {
    dom.generateReportButton.disabled = !hasObservabilityData;
    dom.generateReportButton.title = hasObservabilityData
      ? "Gerar relatorio HTML da rodada atual"
      : "Execute ao menos uma proposta para gerar o relatorio";
  }
}

function buildDisclosureChevron(size = "default") {
  const dimensions = size === "sm" ? "h-4 w-4" : size === "xs" ? "h-3.5 w-3.5" : "h-5 w-5";
  return `<span class="inline-flex h-8 w-8 items-center justify-center rounded border border-slate-200 text-slate-500 dark:border-slate-700 dark:text-slate-400 bg-white dark:bg-slate-900 flex-shrink-0"><svg class="${dimensions} transition-transform duration-200 group-open:rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M9 5l7 7-7 7"></path></svg></span>`;
}

function buildObsChevron() {
  return `<svg class="obs-chevron h-3 w-3 text-slate-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"></path></svg>`;
}

function buildObsStatusDot(tone) {
  const colors = {
    success: "bg-emerald-500",
    danger: "bg-rose-500",
    warning: "bg-amber-500",
    progress: "bg-blue-500",
    neutral: "bg-slate-300 dark:bg-slate-600",
  };
  return `<span class="inline-block h-2 w-2 rounded-full flex-shrink-0 ${colors[tone] || colors.neutral}"></span>`;
}

function buildObsProposalRow(record) {
  const executions = Array.isArray(record.executions) ? [...record.executions].reverse() : [];
  const latest = record.latestExecution || executions[0] || null;
  const tone = getExecutionStatusTone(latest?.status || "");
  const palette = getObservabilityToneClasses(tone);
  const statusLabel = latest ? formatExecutionStatusLabel(latest.status) : "Sem execucoes";
  const processor = (record.processorCode || "-").toUpperCase();
  const agreement = resolveOptionName(state.options.agreements, record.agreementId) || record.agreementId || "-";
  const duration = formatDurationMs(latest?.durationMs || 0);
  const execCount = record.executionCount || executions.length || 0;
  const httpCount = latest?.totalHttpCalls || 0;
  const dbCount = latest?.totalDbChecks || 0;
  const stageCount = latest?.stageResults?.length || 0;

  const stageTimeline = latest?.stageResults?.length
    ? buildObsStageTimeline(latest.stageResults)
    : "";

  return `
    <details class="obs-proposal-row rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm overflow-hidden">
      <summary class="cursor-pointer px-4 py-3 flex items-center gap-3">
        ${buildObsChevron()}
        ${buildObsStatusDot(tone)}
        <span class="text-xs font-bold font-mono text-slate-900 dark:text-white min-w-[60px]">#${escapeHtml(String(record.index || "-"))}</span>
        <span class="inline-flex items-center rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${palette.badge}">${escapeHtml(statusLabel)}</span>
        <span class="text-xs text-slate-500 dark:text-slate-400 truncate hidden sm:inline">${escapeHtml(record.proposalCode || "-")}</span>
        <span class="text-[0.65rem] font-bold text-slate-400 uppercase hidden md:inline">${escapeHtml(processor)}</span>
        <span class="text-xs text-slate-400 hidden lg:inline truncate">${escapeHtml(agreement)}</span>
        <span class="ml-auto flex items-center gap-3 text-[0.65rem] text-slate-400 flex-shrink-0">
          <span title="Etapas">${stageCount} etapas</span>
          <span title="Duracao">${escapeHtml(duration)}</span>
          <span title="HTTP / DB" class="hidden sm:inline">${httpCount}/${dbCount}</span>
          <span title="Execucoes" class="hidden sm:inline">${execCount}x</span>
        </span>
      </summary>

      <div class="border-t border-slate-100 dark:border-slate-800">
        ${stageTimeline ? `
          <div class="px-4 py-3 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/20">
            ${stageTimeline}
          </div>
        ` : ""}

        <div class="divide-y divide-slate-100 dark:divide-slate-800">
          ${executions.map((exec) => buildObsExecutionBlock(exec)).join("")}
        </div>
      </div>
    </details>
  `;
}

function buildObsExecutionBlock(execution) {
  const tone = getExecutionStatusTone(execution?.status || "");
  const palette = getObservabilityToneClasses(tone);
  const stageResults = Array.isArray(execution?.stageResults) ? execution.stageResults : [];
  const statusLabel = formatExecutionStatusLabel(execution?.status || "");
  const started = formatDateTimeLabel(execution?.startedAt || "");
  const finished = formatDateTimeLabel(execution?.finishedAt || "");
  const duration = formatDurationMs(execution?.durationMs || 0);
  const msg = execution?.message || "";

  return `
    <details class="obs-proposal-row group">
      <summary class="cursor-pointer px-4 py-2.5 flex items-center gap-2.5 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
        ${buildObsChevron()}
        ${buildObsStatusDot(tone)}
        <span class="text-[0.65rem] font-mono text-slate-400 flex-shrink-0">${escapeHtml(execution?.runId || "-")}</span>
        <span class="inline-flex items-center rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${palette.badge}">${escapeHtml(statusLabel)}</span>
        ${msg ? `<span class="text-[0.65rem] text-slate-400 truncate hidden md:inline">${escapeHtml(msg)}</span>` : ""}
        <span class="ml-auto flex items-center gap-3 text-[0.65rem] text-slate-400 flex-shrink-0">
          <span>${escapeHtml(duration)}</span>
          <span class="hidden sm:inline">${escapeHtml(started)}</span>
        </span>
      </summary>

      <div class="bg-slate-50/60 dark:bg-slate-950/20">
        <div class="px-4 py-2 flex flex-wrap gap-x-5 gap-y-1 text-[0.65rem] text-slate-400 border-b border-slate-100 dark:border-slate-800">
          <span>Inicio: <strong class="text-slate-600 dark:text-slate-300">${escapeHtml(started)}</strong></span>
          <span>Fim: <strong class="text-slate-600 dark:text-slate-300">${escapeHtml(finished)}</strong></span>
          <span>Duracao: <strong class="text-slate-600 dark:text-slate-300">${escapeHtml(duration)}</strong></span>
          <span>HTTP: <strong class="text-slate-600 dark:text-slate-300">${execution?.totalHttpCalls || 0}</strong></span>
          <span>DB: <strong class="text-slate-600 dark:text-slate-300">${execution?.totalDbChecks || 0}</strong></span>
        </div>

        ${stageResults.length ? `
          <div class="px-4 py-2 space-y-0">
            ${stageResults.map((stage) => buildObsStageItem(stage)).join("")}
          </div>
        ` : `<div class="px-4 py-3 text-[0.65rem] text-slate-400">Sem detalhe de etapas nesta execucao.</div>`}
      </div>
    </details>
  `;
}

function buildObsProtheusValidation(pv) {
  if (!pv) return "";
  const valid = pv.valid === true;
  const bypassed = pv.bypassed === true;
  const checks = Array.isArray(pv.checks) ? pv.checks : [];
  const aiCommentChecks = checks.filter((item) => {
    const label = String(item?.label || "").toUpperCase();
    const origin = String(item?.origin || "").toUpperCase();
    return label.includes("COMENTARIO IA") || origin.includes("AI - COMENTARIO");
  });
  const aiCommentaryItems = aiCommentChecks
    .map((item) => ({
      label: String(item?.label || "Comentario IA"),
      message: String(item?.message || "").trim(),
    }))
    .filter((item) => item.message);
  const visibleChecks = aiCommentChecks.length ? checks.filter((item) => !aiCommentChecks.includes(item)) : checks;

  const headerTone = valid ? "emerald" : "rose";
  const headerIcon = valid
    ? `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>`
    : `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12"/></svg>`;
  const badge = bypassed
    ? `<span class="inline-flex items-center rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400">Bypass</span>`
    : valid
      ? `<span class="inline-flex items-center rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400">Validado</span>`
      : `<span class="inline-flex items-center rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase bg-rose-100 dark:bg-rose-900/30 text-rose-700 dark:text-rose-400">Invalido</span>`;

  const checkRows = visibleChecks.map((c) => {
    const resultIcon = c.result === true
      ? `<span class="text-emerald-500">&#10003;</span>`
      : c.result === false
        ? `<span class="text-rose-500">&#10007;</span>`
        : `<span class="text-slate-400">&mdash;</span>`;
    const sourceTag = c.sourceType === "API"
      ? `<span class="inline-flex items-center rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-1 py-px text-[0.55rem] font-bold uppercase">API</span>`
      : c.sourceType === "SYSTEM"
        ? `<span class="inline-flex items-center rounded bg-slate-100 dark:bg-slate-800 text-slate-500 px-1 py-px text-[0.55rem] font-bold uppercase">SYS</span>`
        : `<span class="inline-flex items-center rounded bg-slate-100 dark:bg-slate-800 text-slate-500 px-1 py-px text-[0.55rem] font-bold uppercase">DB</span>`;

    const querySql = c.querySql || c.query_sql || "";
    const requestHeaders = c.requestHeaders || c.request_headers || "";
    const hasBody = Boolean(querySql || requestHeaders || c.requestBody || c.responseBody);
    const bodyHtml = hasBody ? `
      <tr class="bg-slate-50 dark:bg-slate-900/40">
        <td colspan="4" class="px-2 py-1">
          <details class="text-[0.6rem]">
            <summary class="cursor-pointer text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 select-none">Ver payload</summary>
            <div class="mt-1 space-y-1">
              ${querySql ? `<div><span class="font-bold text-slate-500">Query SQL:</span><pre class="mt-0.5 font-mono text-[0.58rem] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all">${escapeHtml(querySql)}</pre></div>` : ""}
              ${requestHeaders ? `<div><span class="font-bold text-slate-500">Request Headers:</span><pre class="mt-0.5 font-mono text-[0.58rem] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all">${escapeHtml(requestHeaders)}</pre></div>` : ""}
              ${c.requestBody ? `<div><span class="font-bold text-slate-500">Request:</span><pre class="mt-0.5 font-mono text-[0.58rem] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all">${escapeHtml(c.requestBody)}</pre></div>` : ""}
              ${c.responseBody ? `<div><span class="font-bold text-slate-500">Response:</span><pre class="mt-0.5 font-mono text-[0.58rem] bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded p-1.5 overflow-x-auto whitespace-pre-wrap break-all">${escapeHtml(c.responseBody)}</pre></div>` : ""}
            </div>
          </details>
        </td>
      </tr>` : "";

    return `
      <tr class="border-t border-slate-100 dark:border-slate-800">
        <td class="py-1.5 pr-2 w-6 text-center">${resultIcon}</td>
        <td class="py-1.5 pr-2">${sourceTag}</td>
        <td class="py-1.5 pr-2 font-medium text-slate-700 dark:text-slate-300">${escapeHtml(c.label || "-")}</td>
        <td class="py-1.5 text-slate-400 text-[0.6rem] break-all">${escapeHtml(c.message || "")}</td>
      </tr>${bodyHtml}`;
  }).join("");

  return `
    <div class="rounded-lg border border-${headerTone}-200 dark:border-${headerTone}-800/40 overflow-hidden">
      <div class="flex items-center gap-2 px-3 py-2 bg-${headerTone}-50 dark:bg-${headerTone}-950/20 border-b border-${headerTone}-100 dark:border-${headerTone}-800/30">
        <span class="text-${headerTone}-600 dark:text-${headerTone}-400">${headerIcon}</span>
        <span class="text-[0.65rem] font-bold uppercase tracking-wide text-${headerTone}-700 dark:text-${headerTone}-300">
          Validacao Protheus - ${escapeHtml(pv.stageCode || "")}
        </span>
        ${badge}
        <span class="ml-auto text-[0.6rem] text-slate-400">${escapeHtml(pv.message || "")}</span>
      </div>
      ${aiCommentaryItems.length ? `
        <div class="px-3 py-2 bg-blue-50/70 dark:bg-blue-950/20 border-b border-blue-100 dark:border-blue-800/30">
          <span class="text-[0.6rem] font-bold uppercase tracking-wide text-blue-700 dark:text-blue-300">Comentarios IA</span>
          <div class="mt-1 space-y-1">
            ${aiCommentaryItems.map((entry) => {
              const lines = String(entry.message || "").split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
              const title = escapeHtml(entry.label || "Comentario IA");
              return `<div class="text-[0.67rem] leading-relaxed text-slate-600 dark:text-slate-300"><span class="font-bold text-blue-700 dark:text-blue-300">${title}:</span> ${lines.map((line) => escapeHtml(line)).join(" <span class=\"text-slate-300 dark:text-slate-600\">|</span> ")}</div>`;
            }).join("")}
          </div>
        </div>` : ""}
      ${visibleChecks.length ? `
        <div class="overflow-x-auto">
          <table class="obs-log-table">
            <thead><tr>
              <th class="w-6"></th>
              <th>Origem</th>
              <th>Verificacao</th>
              <th>Mensagem</th>
            </tr></thead>
            <tbody>${checkRows}</tbody>
          </table>
        </div>` : ""}
    </div>
  `;
}

function buildObsStageItem(stage) {
  const tone = getExecutionStatusTone(stage?.result || stage?.finalStatus || stage?.initialStatus || "");
  const palette = getObservabilityToneClasses(tone);
  const httpCalls = Array.isArray(stage?.httpCalls) ? stage.httpCalls : [];
  const dbChecks = Array.isArray(stage?.dbChecks) ? stage.dbChecks : [];
  const notes = Array.isArray(stage?.notes) ? stage.notes.filter(Boolean) : [];
  const protheusValidation = stage?.protheusValidation || null;
  const hasDetails = httpCalls.length > 0 || dbChecks.length > 0 || notes.length > 0 || protheusValidation !== null;
  const statusResult = stage?.result || stage?.finalStatus || "";
  const action = formatConfiguredActionLabel(stage?.configuredAction || "");
  const duration = formatDurationMs(stage?.durationMs || 0);
  const initialStatus = formatHistoryFlowStatus(stage?.initialStatus || "-");
  const finalStatus = formatHistoryFlowStatus(stage?.finalStatus || "-");

  const inner = `
    <div class="obs-stage-item tone-${tone} pl-3 py-2 pr-3 flex items-start gap-2 ${hasDetails ? "cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/30 transition-colors" : ""}">
      ${hasDetails ? buildObsChevron() : `<span class="inline-block w-3 flex-shrink-0"></span>`}
      ${buildObsStatusDot(tone)}
      <div class="flex-1 min-w-0 flex flex-wrap items-baseline gap-x-3 gap-y-0.5">
        <span class="text-[0.65rem] font-mono font-bold text-slate-500 dark:text-slate-400 uppercase">${escapeHtml(stage?.stageCode || "-")}</span>
        <span class="text-xs font-medium text-slate-800 dark:text-slate-200">${escapeHtml(stage?.stageName || "Etapa")}</span>
        <span class="inline-flex items-center rounded px-1.5 py-0.5 text-[0.6rem] font-bold uppercase tracking-wide ${palette.badge}">${escapeHtml(formatExecutionStatusLabel(statusResult))}</span>
        ${stage?.message ? `<span class="text-[0.65rem] text-slate-400 truncate">${escapeHtml(stage.message)}</span>` : ""}
      </div>
      <div class="flex items-center gap-3 text-[0.65rem] text-slate-400 flex-shrink-0 whitespace-nowrap">
        <span class="hidden lg:inline">${escapeHtml(action)}</span>
        <span class="hidden md:inline">${escapeHtml(initialStatus)} &rarr; ${escapeHtml(finalStatus)}</span>
        <span>${escapeHtml(duration)}</span>
      </div>
    </div>
  `;

  if (!hasDetails) return inner;

  return `
    <details class="obs-proposal-row group">
      <summary class="list-none">${inner}</summary>
      <div class="ml-6 mr-2 mb-2 space-y-2">
        ${notes.length ? `
          <div class="flex flex-wrap gap-1 px-2 pt-1">
            ${notes.map((n) => `<span class="inline-flex items-center rounded bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[0.6rem] text-slate-500 dark:text-slate-400">${escapeHtml(n)}</span>`).join("")}
          </div>
        ` : ""}
        ${httpCalls.length ? buildObsHttpTable(httpCalls) : ""}
        ${dbChecks.length ? buildObsDbTable(dbChecks) : ""}
        ${protheusValidation ? buildObsProtheusValidation(protheusValidation) : ""}
      </div>
    </details>
  `;
}

function buildObsHttpTable(calls) {
  const rows = calls.map((c) => `
    <tr>
      <td><span class="inline-flex items-center rounded bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900 px-1 py-px text-[0.6rem] font-bold uppercase">${escapeHtml(c.method || "GET")}</span></td>
      <td class="font-medium text-slate-700 dark:text-slate-300">${escapeHtml(c.label || "-")}</td>
      <td class="font-mono break-all text-slate-400 max-w-[260px]">${escapeHtml(c.path || "-")}</td>
      <td class="text-center">${escapeHtml(String(c.statusCode ?? "-"))}</td>
      <td class="text-right">${escapeHtml(formatDurationMs(c.durationMs || 0))}</td>
      <td class="text-right whitespace-nowrap">${escapeHtml(formatDateTimeLabel(c.timestamp || ""))}</td>
    </tr>
  `).join("");

  return `
    <div class="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden">
      <div class="px-2 py-1.5 bg-slate-50 dark:bg-slate-800/60 text-[0.6rem] font-bold uppercase tracking-wide text-slate-400">Requests HTTP (${calls.length})</div>
      <div class="overflow-x-auto">
        <table class="obs-log-table">
          <thead><tr><th></th><th>Label</th><th>Path</th><th>Status</th><th class="text-right">Duracao</th><th class="text-right">Horario</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function buildObsDbTable(checks) {
  const rows = checks.map((c) => {
    const matchClass = c.matched === true
      ? "text-emerald-600 dark:text-emerald-400"
      : c.matched === false
      ? "text-amber-600 dark:text-amber-400"
      : "text-slate-400";
    const matchLabel = c.matched === true ? "Sim" : c.matched === false ? "Nao" : "-";
    const sql = c.query_sql || c.querySql || "";

    return `
      <tr>
        <td class="font-medium text-slate-700 dark:text-slate-300 whitespace-nowrap">${escapeHtml(c.label || c.queryName || "-")}</td>
        <td class="font-mono text-slate-400 whitespace-nowrap">${escapeHtml(c.queryName || c.query_name || "-")}</td>
        <td>${sql ? `<code class="block font-mono text-[0.6rem] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 rounded px-1.5 py-1 whitespace-pre-wrap break-all">${escapeHtml(sql)}</code>` : `<span class="text-slate-300 dark:text-slate-600">-</span>`}</td>
        <td class="text-center font-bold ${matchClass} whitespace-nowrap">${matchLabel}</td>
        <td class="text-right whitespace-nowrap">${escapeHtml(formatDurationMs(c.durationMs || c.duration_ms || 0))}</td>
        <td class="text-right whitespace-nowrap">${escapeHtml(formatDateTimeLabel(c.timestamp || ""))}</td>
      </tr>
    `;
  }).join("");

  return `
    <div class="rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden">
      <div class="px-2 py-1.5 bg-slate-50 dark:bg-slate-800/60 text-[0.6rem] font-bold uppercase tracking-wide text-slate-400">Validacoes DB (${checks.length})</div>
      <div class="overflow-x-auto">
        <table class="obs-log-table">
          <thead><tr><th>Label</th><th>Tabela</th><th>SQL</th><th class="text-center">Match</th><th class="text-right">Duracao</th><th class="text-right">Horario</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>
  `;
}

function buildObsStageTimeline(stageResults) {
  const nodes = stageResults.map((stage, i) => {
    const visual = getHistoryFlowStageVisual(stage.finalStatus || stage.result || stage.initialStatus);
    const name = escapeHtml(stage.stageName || "Etapa");
    const isLast = i === stageResults.length - 1;
    return `
      <div class="relative min-w-[90px] max-w-[100px] px-0.5" title="${name}">
        <div class="relative h-4 mb-1.5">
          ${isLast ? "" : `<span class="absolute h-px rounded-full ${visual.lineClass}" style="left:calc(50% + 8px);right:-50%;top:50%;transform:translateY(-50%)"></span>`}
          <div class="absolute h-3.5 w-3.5 rounded-full border-2 ${visual.nodeBorderClass} bg-white dark:bg-slate-950 flex items-center justify-center z-10" style="left:50%;top:50%;transform:translate(-50%,-50%)">
            <span class="h-1.5 w-1.5 rounded-full ${visual.dotClass}"></span>
          </div>
        </div>
        <span class="block text-[0.6rem] leading-tight text-center text-slate-500 dark:text-slate-400">${name}</span>
      </div>
    `;
  }).join("");

  return `
    <div class="overflow-x-auto">
      <div class="min-w-max flex items-start gap-0">${nodes}</div>
    </div>
  `;
}

function getObservabilityToneClasses(tone) {
  const palette = {
    neutral: {
      softBorder: "border-slate-200 dark:border-slate-800",
      softBackground: "bg-white dark:bg-slate-900",
      eyebrow: "text-slate-400",
      badge: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    },
    progress: {
      softBorder: "border-blue-200 dark:border-blue-800/50",
      softBackground: "bg-blue-50/70 dark:bg-blue-950/20",
      eyebrow: "text-blue-500 dark:text-blue-400",
      badge: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300",
    },
    warning: {
      softBorder: "border-amber-200 dark:border-amber-800/50",
      softBackground: "bg-amber-50/70 dark:bg-amber-950/20",
      eyebrow: "text-amber-500 dark:text-amber-400",
      badge: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300",
    },
    success: {
      softBorder: "border-emerald-200 dark:border-emerald-800/50",
      softBackground: "bg-emerald-50/70 dark:bg-emerald-950/20",
      eyebrow: "text-emerald-500 dark:text-emerald-400",
      badge: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300",
    },
    danger: {
      softBorder: "border-rose-200 dark:border-rose-800/50",
      softBackground: "bg-rose-50/70 dark:bg-rose-950/20",
      eyebrow: "text-rose-500 dark:text-rose-400",
      badge: "bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300",
    },
  };

  return palette[tone] || palette.neutral;
}

function getExecutionStatusTone(status) {
  const normalized = String(status || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();

  if (!normalized) return "neutral";
  if (/(fail|failed|erro|error|reject|reprov|denied|invalid|not_found)/.test(normalized)) return "danger";
  if (/(cancel|manual|wait|waiting|timeout|penden|alert|warn|review)/.test(normalized)) return "warning";
  if (/(in_progress|in progress|processing|processando|running|started|start)/.test(normalized)) return "progress";
  if (/(approved|success|done|completed|complete|finished|finish|ok|validated)/.test(normalized)) return "success";
  return "neutral";
}

function formatExecutionStatusLabel(status) {
  const normalized = String(status || "").trim();
  if (!normalized) return "Sem status";
  return normalized
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatConfiguredActionLabel(action) {
  const normalized = String(action || "").toLowerCase();
  if (normalized === "wait") return "Aguardar";
  if (normalized === "manual") return "Manual";
  if (normalized === "finish") return "Finalizar";
  if (normalized === "db_check") return "Validacao DB";
  return normalized ? formatExecutionStatusLabel(normalized) : "Nao definido";
}

function formatDurationMs(value) {
  const totalMs = Number(value || 0);
  if (!Number.isFinite(totalMs) || totalMs <= 0) {
    return "-";
  }
  if (totalMs < 1000) {
    return `${Math.round(totalMs)} ms`;
  }
  const totalSeconds = Math.round(totalMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function formatDateTimeLabel(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// ==========================================================================
// FLOW MODAL - Matriz de Avalia--o
// ==========================================================================

let _flowModalIndex = null;
let _flowModalDraft = {};
let _flowModalRecord = null;
let _flowModalFlow = null;

function resetFlowModalScroll() {
  if (!dom.flowModalBody) {
    return;
  }
  dom.flowModalBody.scrollTop = 0;
}


async function openFlowModal(index) {
  const record = state.proposalHistory.find((r) => r.index === index);
  if (!record) {
    setStatusBanner("Nao foi possivel localizar a proposta selecionada.", "warning");
    return;
  }

  _flowModalIndex = index;
  _flowModalDraft = {};
  _flowModalRecord = null;
  _flowModalFlow = null;
  dom.flowModalSubtitle.textContent = `Proposta #${index} - Contrato ${record.contractCode || record.simulationCode}`;
  dom.flowModalBody.innerHTML = `
    <div class="py-10 flex flex-col items-center justify-center gap-3 text-sm text-slate-500 dark:text-slate-400">
      <span class="inline-block h-6 w-6 rounded-full border-2 border-slate-300 dark:border-slate-600 border-t-blue-600 animate-spin"></span>
      <span>Consultando as etapas da esteira...</span>
    </div>
  `;
  dom.flowModalConfirm.disabled = true;
  dom.flowModal.classList.remove("is-hidden");
  resetFlowModalScroll();

  let flow = record.flow;
  const hasStages = flow && Array.isArray(flow.stages) && flow.stages.length > 0;

  if (!hasStages) {
    try {
      flow = await ensureProposalFlow(index);
    } catch (error) {
      if (_flowModalIndex !== index) {
        return;
      }
      dom.flowModalBody.innerHTML = `
        <div class="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
          Nao consegui carregar as etapas desta proposta agora.
        </div>
      `;
      dom.flowModalConfirm.disabled = true;
      resetFlowModalScroll();
      setStatusBanner(error?.detail || "Nao consegui carregar as etapas desta proposta agora.", "warning");
      return;
    }
  }

  if (_flowModalIndex !== index) {
    return;
  }

  _flowModalRecord = record;
  _flowModalFlow = flow;
  renderFlowModalContent(index, record, flow);
}

async function ensureProposalFlow(index, forceRefresh = false) {
  const payload = await apiRequest("/api/proposal-history/flow", {
    method: "POST",
    body: JSON.stringify({
      environment: state.environment,
      historyIndex: index,
      forceRefresh,
    }),
  });

  const record = state.proposalHistory.find((item) => item.index === index);
  if (record) {
    record.flow = payload.flow || null;
    if (record.flow) {
      syncFlowConfigWithLatestFlow(record, record.flow);
    }
  }

  return payload.flow || null;
}

function getFlowConfigKey(record, flow) {
  const proposalId = String(record?.proposalId || flow?.proposalId || "").trim();
  const flowId = String(flow?.flowId || "").trim();
  return `${proposalId || "proposal"}:${flowId || "flow"}`;
}

function getSavedFlowConfig(record, flow) {
  return state.flowConfigs[getFlowConfigKey(record, flow)] || null;
}

function getSavedFlowActions(record, flow) {
  const saved = getSavedFlowConfig(record, flow);
  if (!saved || !Array.isArray(saved.stages)) {
    return {};
  }

  return saved.stages.reduce((accumulator, stage) => {
    const stageId = String(stage.stageId || "");
    if (stageId) {
      accumulator[stageId] = stage.action || "wait";
    }
    return accumulator;
  }, {});
}

function buildFlowConfigSnapshot(record, flow, actionsByStageId) {
  return {
    environment: state.environment,
    historyIndex: record?.index ?? null,
    proposalId: String(record?.proposalId || flow?.proposalId || ""),
    proposalCode: String(record?.proposalCode || ""),
    contractCode: String(record?.contractCode || ""),
    flowId: String(flow?.flowId || ""),
    stages: (flow?.stages || []).map((stage, index) => ({
      order: index + 1,
      stageId: String(stage.id || ""),
      stageCode: String(stage.code || ""),
      stageName: String(stage.name || ""),
      stageStatus: String(stage.status || ""),
      action: actionsByStageId[String(stage.id || "")] || "wait",
    })),
    updatedAt: new Date().toISOString(),
  };
}

function saveFlowConfig(record, flow, actionsByStageId) {
  const snapshot = buildFlowConfigSnapshot(record, flow, actionsByStageId);
  state.flowConfigs[getFlowConfigKey(record, flow)] = snapshot;
  return snapshot;
}

function syncFlowConfigWithLatestFlow(record, flow) {
  const savedActions = getSavedFlowActions(record, flow);
  if (!Object.keys(savedActions).length) {
    return null;
  }
  return saveFlowConfig(record, flow, savedActions);
}

function _flowColWidth() {
  return window.innerWidth <= 540 ? "180px" : "264px";
}

function _syncFlowColHeader() {
  if (dom.flowColHeader) {
    dom.flowColHeader.style.width = _flowColWidth();
  }
}

function renderFlowModalContent(index, record, flow) {
  _syncFlowColHeader();
  if (!flow || !Array.isArray(flow.stages) || !flow.stages.length) {
    dom.flowModalBody.innerHTML = `
      <div class="py-8 text-center text-sm text-slate-500 dark:text-slate-400">
        O dashboard ainda nao retornou etapas para esta proposta.
      </div>
    `;
    dom.flowModalConfirm.disabled = true;
    resetFlowModalScroll();
    return;
  }

  const savedActions = getSavedFlowActions(record, flow);
  _flowModalDraft = {};

  const totalStages = flow.stages.length;
  const colW = _flowColWidth();
  const stagesHtml = flow.stages.map((stage, i) => {
    const current = savedActions[stage.id] || "wait";
    _flowModalDraft[stage.id] = current;
    const isLast = i === totalStages - 1;

    const dotColor = current === "wait"
      ? "bg-amber-400 dark:bg-amber-500"
      : current === "manual"
        ? "bg-blue-400 dark:bg-blue-500"
        : "bg-emerald-400 dark:bg-emerald-500";

    return `<div class="grid items-center" style="grid-template-columns: 1fr auto;" data-flow-stage-row="${stage.id}">
      <div class="flex items-start gap-3 py-3">
        <div class="flex flex-col items-center shrink-0" style="width: 14px;">
          <div class="flow-dot w-3 h-3 rounded-full ${dotColor} ring-2 ring-white dark:ring-slate-900 shrink-0 mt-0.5"></div>
          ${isLast ? "" : `<div class="w-px flex-1 bg-slate-200 dark:bg-slate-700 mt-1" style="min-height: 24px;"></div>`}
        </div>
        <div class="flex flex-col justify-center min-w-0 -mt-0.5">
          <span class="text-xs font-bold text-slate-900 dark:text-white leading-tight">${stage.name}</span>
          <span class="text-[0.6rem] text-slate-400 font-mono mt-0.5">${stage.code}</span>
        </div>
      </div>
      <div class="grid grid-cols-3 gap-0" style="width: ${colW};">
        ${_flowRadio(stage.id, "wait", current)}
        ${_flowRadio(stage.id, "manual", current)}
        ${_flowRadio(stage.id, "finish", current)}
      </div>
    </div>`;
  });

  dom.flowModalBody.innerHTML = stagesHtml.join("");
  dom.flowModalConfirm.disabled = false;
  resetFlowModalScroll();

  dom.flowModalBody.querySelectorAll(".flow-choice-btn").forEach((btn) => {
    btn.addEventListener("click", handleFlowChoiceClick);
  });
}

function _flowRadio(stageId, value, current) {
  const active = current === value;
  const colors = {
    wait: {
      on: "bg-amber-100 dark:bg-amber-900/30 border-amber-300 dark:border-amber-600 text-amber-600 dark:text-amber-300",
      dot: "bg-amber-500",
    },
    manual: {
      on: "bg-blue-100 dark:bg-blue-900/30 border-blue-300 dark:border-blue-600 text-blue-600 dark:text-blue-300",
      dot: "bg-blue-500",
    },
    finish: {
      on: "bg-emerald-100 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-600 text-emerald-600 dark:text-emerald-300",
      dot: "bg-emerald-500",
    },
  };
  const c = colors[value];
  const cls = active
    ? c.on
    : "bg-transparent border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800";
  const dot = active
    ? `<span class="w-2 h-2 rounded-full ${c.dot}"></span>`
    : `<span class="w-2 h-2 rounded-full border border-slate-300 dark:border-slate-600"></span>`;

  return `<button type="button" class="flow-choice-btn flex items-center justify-center gap-1.5 py-2 border ${cls} text-[0.65rem] font-semibold transition-colors cursor-pointer" data-stage-id="${stageId}" data-value="${value}">${dot}</button>`;
}

function handleFlowChoiceClick(event) {
  const btn = event.currentTarget;
  const stageId = btn.dataset.stageId;
  const value = btn.dataset.value;

  _flowModalDraft[stageId] = value;

  const row = btn.closest("[data-flow-stage-row]");

  row.querySelectorAll(".flow-choice-btn").forEach((b) => {
    const v = b.dataset.value;
    const isActive = v === value;
    const colors = {
      wait: {
        on: "bg-amber-100 dark:bg-amber-900/30 border-amber-300 dark:border-amber-600 text-amber-600 dark:text-amber-300",
        dot: "bg-amber-500",
      },
      manual: {
        on: "bg-blue-100 dark:bg-blue-900/30 border-blue-300 dark:border-blue-600 text-blue-600 dark:text-blue-300",
        dot: "bg-blue-500",
      },
      finish: {
        on: "bg-emerald-100 dark:bg-emerald-900/30 border-emerald-300 dark:border-emerald-600 text-emerald-600 dark:text-emerald-300",
        dot: "bg-emerald-500",
      },
    };
    const c = colors[v];
    const cls = isActive
      ? c.on
      : "bg-transparent border-slate-200 dark:border-slate-700 text-slate-400 dark:text-slate-500 hover:bg-slate-50 dark:hover:bg-slate-800";

    b.className = `flow-choice-btn flex items-center justify-center gap-1.5 py-2 border ${cls} text-[0.65rem] font-semibold transition-colors cursor-pointer`;

    const dotEl = b.querySelector("span");
    if (dotEl) {
      dotEl.className = isActive
        ? `w-2 h-2 rounded-full ${c.dot}`
        : "w-2 h-2 rounded-full border border-slate-300 dark:border-slate-600";
    }
  });

  const dotEl = row.querySelector(".flow-dot");
  if (dotEl) {
    dotEl.className = `flow-dot w-3 h-3 rounded-full ring-2 ring-white dark:ring-slate-900 shrink-0 mt-0.5 ${
      value === "wait" ? "bg-amber-400 dark:bg-amber-500"
        : value === "manual" ? "bg-blue-400 dark:bg-blue-500"
          : "bg-emerald-400 dark:bg-emerald-500"
    }`;
  }
}

function closeFlowModal() {
  dom.flowModal.classList.add("is-hidden");
  dom.flowModalConfirm.disabled = false;
  _flowModalIndex = null;
  _flowModalDraft = {};
  _flowModalRecord = null;
  _flowModalFlow = null;
}

function handleFlowModalConfirm() {
  if (_flowModalIndex == null || !_flowModalRecord || !_flowModalFlow) return;

  saveFlowConfig(_flowModalRecord, _flowModalFlow, _flowModalDraft);
  closeFlowModal();
  setStatusBanner("Configuracoes aplicadas.", "success");
}

function handleFlowModalCancel() {
  closeFlowModal();
  setStatusBanner("Configuracoes canceladas.", "info");
}
function resolveOptionName(options, id) {
  if (!options || !id) return "";
  const item = options.find((opt) => String(opt.id) === String(id));
  return item?.name || "";
}

function formatCpf(document) {
  const digits = sanitizeDigits(document || "");
  if (digits.length !== 11) return digits || "-";
  return `${digits.slice(0, 3)}.${digits.slice(3, 6)}.${digits.slice(6, 9)}-${digits.slice(9)}`;
}

async function clearServerHistory() {
  try {
    await apiRequest("/api/proposal-history", { method: "DELETE" });
  } catch {
    // silently ignore - history will just carry over
  }
}

function buildOptimisticProposalHistoryRecord(payload) {
  const summary = payload?.summary;
  if (!summary) {
    return null;
  }

  return {
    index: Number(payload?.historyIndex || state.proposalHistory.length + 1),
    createdAt: new Date().toISOString(),
    proposalId: String(summary.id || ""),
    proposalCode: String(summary.code || state.simulation?.code || ""),
    contractCode: String(summary.contractCode || ""),
    simulationId: String(state.simulation?.id || ""),
    simulationCode: String(summary.simulationCode || summary.code || state.simulation?.code || ""),
    clientId: String(state.simulationRaw?.data?.client_id || ""),
    clientName: dom.clientNameInput.value.trim() || state.preview?.nome || "",
    clientDocument: sanitizeDigits(dom.clientDocumentInput.value || state.preview?.cpf || ""),
    agreementId: state.selections.agreementId,
    productId: state.selections.productId,
    saleModalityId: state.selections.saleModalityId,
    withdrawTypeId: state.selections.withdrawTypeId,
    processorCode: state.processorCode || "",
    flow: null,
  };
}

function upsertProposalHistoryRecord(record) {
  if (!record) {
    return;
  }

  const nextRecords = Array.isArray(state.proposalHistory) ? [...state.proposalHistory] : [];
  const index = nextRecords.findIndex((item) => String(item.index) === String(record.index));
  if (index >= 0) {
    nextRecords[index] = {
      ...nextRecords[index],
      ...record,
    };
  } else {
    nextRecords.push(record);
  }

  nextRecords.sort((left, right) => Number(left.index || 0) - Number(right.index || 0));
  state.proposalHistory = nextRecords;
}
async function fetchProposalHistory({ preserveCurrentOnEmpty = false } = {}) {
  if (!state.connected || !state.environment) return false;

  const previousRecords = Array.isArray(state.proposalHistory) ? [...state.proposalHistory] : [];
  const previousSummary = state.observabilitySummary || buildEmptyObservabilitySummary();

  try {
    const payload = await apiRequest(`/api/proposal-history?environment=${encodeURIComponent(state.environment)}`);
    const proposals = Array.isArray(payload.proposals) ? payload.proposals : [];
    const summary = payload.observabilitySummary && typeof payload.observabilitySummary === "object"
      ? { ...buildEmptyObservabilitySummary(), ...payload.observabilitySummary }
      : buildEmptyObservabilitySummary();

    if (proposals.length || !preserveCurrentOnEmpty) {
      state.proposalHistory = proposals;
    } else {
      state.proposalHistory = previousRecords;
    }
    state.observabilitySummary = summary;
  } catch {
    state.proposalHistory = preserveCurrentOnEmpty ? previousRecords : [];
    state.observabilitySummary = preserveCurrentOnEmpty ? previousSummary : buildEmptyObservabilitySummary();
  }

  renderHistory();
  renderObservability();
  renderStepSubtexts();
  renderJourneyIndicators();
  return state.proposalHistory.length > 0;
}

// ==========================================================================
// NOVAS FUN--ES - REIMAGINACAO UX
// ==========================================================================

function renderStepSubtexts() {
  const totalExecutions = Number(state.observabilitySummary?.totalExecutions || 0);
  const subtexts = {
    overviewSection: state.connected
      ? (state.environment?.toUpperCase() || "")
      : "Aguardando conexao",
    simulationSection: state.simulation
      ? `ID ${state.simulation.id}`
      : state.preview
        ? `${(state.processorCode || "").toUpperCase()} - base pronta`
        : state.connected
          ? "Escolha convenio e produto"
          : "Aguardando conexao",
    proposalSection: state.proposal
      ? `Contrato ${state.proposal.contractCode}`
      : state.simulation
        ? "Pronta para emitir"
        : "Aguardando simulacao",
    resultsSection: state.proposal
      ? `Proposta ${state.proposal.code || state.proposal.contractCode || ""}`
      : state.simulation
        ? "Aguardando proposta"
        : "Aguardando",
    historySection: state.proposalHistory.length > 0
      ? `${state.proposalHistory.length} proposta(s)`
      : "Nenhuma proposta",
    observabilitySection: totalExecutions > 0
      ? `${totalExecutions} execucao(oes)`
      : state.proposalHistory.length > 0
        ? "Pronto para observar"
        : "Sem execucoes",
  };

  dom.navItems.forEach((item) => {
    const sub = item.querySelector(".step-body-sub");
    if (sub && subtexts[item.dataset.scrollTarget]) {
      sub.textContent = subtexts[item.dataset.scrollTarget];
    }
  });
}

function renderSectionLocks() {
  const proposalSection = document.getElementById("proposalSection");
  if (proposalSection) {
    proposalSection.classList.toggle(
      "is-locked",
      !state.simulation && state.simulationStatus !== "running"
    );
  }
}

function renderProcessorContextBlock() {
  const block = document.getElementById("sidebarContextBlock");
  if (!block) return;

  if (!state.processorCode) {
    block.classList.add("is-hidden");
    return;
  }

  block.classList.remove("is-hidden");
  const badge = document.getElementById("sidebarProcessorBadge");
  if (badge) {
    badge.textContent = state.processorCode.toUpperCase();
    const normalized = state.processorCode.toLowerCase().replace(/[^a-z]/g, "");
    badge.className = `processor-icon-badge badge-${normalized}`;
  }
}

function renderProcessorZoneEmpty() {
  const empty = document.getElementById("processorZoneEmpty");
  if (!empty) return;

  const anyVisible =
    !dom.cipPanel.classList.contains("is-hidden") ||
    !dom.zetraPanel.classList.contains("is-hidden") ||
    !dom.serproPanel.classList.contains("is-hidden") ||
    !dom.ccbPanel.classList.contains("is-hidden");

  empty.classList.toggle("is-hidden", anyVisible);
}

function showPreviewSkeleton() {
  dom.previewPlaceholder.classList.add("is-hidden");
  dom.previewCard.classList.remove("is-hidden");

  [dom.previewWorksheetTitle, dom.previewBalanceValue, dom.previewCpfValue, dom.previewMatricula].forEach((el) => {
    if (el) {
      el.innerHTML = '<span class="skeleton-line" style="width:78%"></span>';
    }
  });
}

function setupCopyButtons() {
  const copiedIconMarkup = '<svg class="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.4" d="M5 13l4 4L19 7"></path></svg>';

  document.querySelectorAll(".copy-btn").forEach((btn) => {
    if (!btn.dataset.originalMarkup) {
      btn.dataset.originalMarkup = btn.innerHTML;
    }

    btn.addEventListener("click", () => {
      const source = document.getElementById(btn.dataset.copyTarget);
      if (!source || !source.textContent || source.textContent === "Aguardando") return;

      navigator.clipboard.writeText(source.textContent.trim()).then(() => {
        btn.classList.add("copied");
        btn.innerHTML = copiedIconMarkup;
        setTimeout(() => {
          btn.classList.remove("copied");
          btn.innerHTML = btn.dataset.originalMarkup || copiedIconMarkup;
        }, 1800);
      }).catch(() => {
        /* fallback silencioso - clipboard indisponivel */
      });
    });
  });
}

