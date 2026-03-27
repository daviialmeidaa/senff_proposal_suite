const state = {
  environments: [],
  environment: "",
  connected: false,
  branding: {
    logoUrl: "",
    iconUrl: "",
    title: "Suite Consignado",
    subtitle: "Simulacoes e propostas",
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
  nameMode: "manual",
  phoneMode: "manual",
};

const dom = {};
let sectionObserver = null;

document.addEventListener("DOMContentLoaded", async () => {
  cacheDom();
  bindEvents();
  restoreSidebarState();
  applyStoredTheme();
  updateModeButtons("name", state.nameMode);
  updateModeButtons("phone", state.phoneMode);
  await Promise.all([loadAppConfig(), loadEnvironments()]);
  setupSectionObserver();
  renderAll();
});

function cacheDom() {
  dom.appFavicon = document.getElementById("appFavicon");
  dom.sidebarLogo = document.getElementById("sidebarLogo");

  dom.headerSidebarToggle = document.getElementById("headerSidebarToggle");
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
  dom.sidebarSimulationCode = document.getElementById("sidebarSimulationCode");
  dom.sidebarProposalCode = document.getElementById("sidebarProposalCode");
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

  dom.proposalSimulationRef = document.getElementById("proposalSimulationRef");
  dom.proposalMainDocument = document.getElementById("proposalMainDocument");
  dom.proposalBenefitPreview = document.getElementById("proposalBenefitPreview");
  dom.proposalDocumentPreview = document.getElementById("proposalDocumentPreview");
  dom.proposalEmailPreview = document.getElementById("proposalEmailPreview");

  dom.simulationCard = document.getElementById("simulationCard");
  dom.resultCode = document.getElementById("resultCode");
  dom.resultNarrative = document.getElementById("resultNarrative");
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
}

function bindEvents() {
  dom.environmentButtons.addEventListener("click", handleEnvironmentClick);
  dom.connectButton.addEventListener("click", handleConnect);
  dom.previewButton.addEventListener("click", handlePreview);
  dom.simulateButton.addEventListener("click", handleSimulate);
  dom.proposalButton.addEventListener("click", handleProposal);
  dom.newProposalButton.addEventListener("click", handleStartNextProposal);

  dom.headerSidebarToggle.addEventListener("click", toggleSidebar);

  dom.navItems.forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.dataset.scrollTarget;
      const section = document.getElementById(targetId);
      if (section) {
        section.scrollIntoView({ behavior: "smooth", block: "start" });
        setActiveNav(targetId);
      }
      if (window.innerWidth <= 980) {
        setSidebarCollapsed(true);
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
  dom.sidebarLogo.src = "./assets/logo.svg";
  dom.sidebarLogo.classList.remove("is-hidden");

  if (state.branding.iconUrl) {
    dom.appFavicon.href = state.branding.iconUrl;
  }

  document.title = `${state.branding.title || "Suite Consignado"} | ${state.branding.subtitle || "Simulacoes e propostas"}`;
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
  renderActionState();
  renderStatusCopy();
  renderJourneyIndicators();
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
  const previous = selectedValue || select.value || "";
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
  dom.sidebarSimulationCode.textContent = state.simulation?.code || "-";
  dom.sidebarProposalCode.textContent = state.proposal?.code || "-";
}

function renderPreview() {
  if (!state.preview) {
    dom.previewPlaceholder.classList.remove("is-hidden");
    dom.previewCard.classList.add("is-hidden");
    return;
  }

  dom.previewPlaceholder.classList.add("is-hidden");
  dom.previewCard.classList.remove("is-hidden");
  dom.previewProcessorBadge.textContent = (state.processorCode || state.preview.processorCode || "-").toUpperCase();
  dom.previewWorksheetTitle.textContent = state.preview.worksheetName || "-";
  dom.previewBalanceValue.textContent = formatBalanceValue(state.preview.balanceValue);
  dom.previewCpfValue.textContent = state.preview.maskedCpf || maskDigits(state.preview.cpf);
  dom.previewMatricula.textContent = state.preview.matricula || "Nao informada";
  dom.previewHelperText.textContent = buildPreviewNarrative();
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
  if (!dom.userPasswordInput.value && state.preview.senha) {
    dom.userPasswordInput.value = state.preview.senha;
  }

  if (isZetraProcessor()) {
    dom.zetraHint.textContent = state.preview.senha
      ? "Matricula e senha ja vieram da base. Edite apenas se precisar de fallback manual."
      : "A matricula da base sera usada automaticamente. A senha e opcional.";
  }
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

  dom.proposalSimulationRef.textContent = state.simulation?.code || "Aguardando simulacao";
  dom.proposalMainDocument.textContent = currentDocument ? maskDigits(currentDocument) : "-";
  dom.proposalBenefitPreview.textContent = currentBenefitNumber || "-";
  dom.proposalDocumentPreview.textContent = state.proposalGenerated?.contractDocumentMasked
    ? `${generatedType} - ${state.proposalGenerated.contractDocumentMasked}`
    : generatedType;
  dom.proposalEmailPreview.textContent = generatedEmail;
}

function renderResults() {
  renderSimulationResult();
  renderProposalResult();
}

function renderSimulationResult() {
  const selectedAgreement = getSelectedItem(state.options.agreements, state.selections.agreementId);
  const selectedEnvironment = state.environments.find((item) => item.key === state.environment);
  const hasSimulation = Boolean(state.simulation);

  dom.simulationCard.classList.toggle("empty-result", !hasSimulation);
  dom.resultCode.textContent = hasSimulation ? state.simulation.code || "Sem codigo" : "Aguardando";
  dom.resultNarrative.textContent = hasSimulation
    ? `${selectedEnvironment?.label || "-"} - ${selectedAgreement?.name || "Caso atual"}`
    : "A simulacao aparece aqui.";
  dom.resultRequestedValue.textContent = hasSimulation ? formatCents(state.simulation.requestedValue) : "-";
  dom.resultInstallmentValue.textContent = hasSimulation ? formatCents(state.simulation.installmentValue) : "-";
  dom.resultDeadline.textContent = hasSimulation && state.simulation.deadline ? `${state.simulation.deadline} meses` : "-";
  dom.resultMarginValue.textContent = hasSimulation ? formatCents(state.simulation.marginValue) : "-";
}

function renderProposalResult() {
  const hasProposal = Boolean(state.proposal);
  dom.proposalCard.classList.toggle("empty-result", !hasProposal);
  dom.proposalCode.textContent = hasProposal ? state.proposal.code || "Sem codigo" : "Aguardando";
  dom.proposalNarrative.textContent = hasProposal
    ? `${state.proposal.clientName || "Cliente"} - vinculada a ${state.proposal.simulationCode || "simulacao atual"}`
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

function buildJourneyStatus() {
  if (!state.connected) {
    return "Conecte um ambiente para comecar.";
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
  return "Proposta emitida com sucesso. Se quiser, inicie uma nova proposta.";
}

function renderActionState() {
  dom.previewButton.disabled = !(state.connected && state.selections.agreementId && state.selections.productId);
  dom.simulateButton.disabled = !isSimulationReady();
  dom.proposalButton.disabled = !isProposalReady() || Boolean(state.proposal);
}

function renderProposalFeedback() {
  dom.proposalActionCard.classList.remove("is-success", "is-error");
  dom.proposalCard.classList.remove("is-success", "is-error");

  if (state.proposalStatus === "success" && state.proposal) {
    dom.proposalStatusBanner.className = "inline-status success";
    dom.proposalStatusBanner.textContent = `Proposta emitida com sucesso. Codigo ${state.proposal.code || "sem codigo"}.`;
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

  try {
    const payload = await withBusyButton(dom.previewButton, "Consultando...", () => {
      return apiRequest("/api/session/preview", {
        method: "POST",
        body: JSON.stringify({
          environment: state.environment,
          agreementId: state.selections.agreementId,
          productId: state.selections.productId,
        }),
      });
    });

    state.processorCode = payload.processorCode || "";
    state.preview = payload.record || null;
    dom.clientDocumentInput.value = sanitizeDigits(state.preview?.cpf || "");
    dom.documentHelper.textContent = dom.clientDocumentInput.value
      ? "CPF carregado da base."
      : "A base nao retornou CPF para este caso.";

    if (state.nameMode === "faker" && !dom.clientNameInput.value) {
      await fillWithFaker("name");
    }
    if (state.phoneMode === "faker" && !dom.clientPhoneInput.value) {
      await fillWithFaker("phone");
    }

    setStatusBanner("Base pronta. Revise o caso e siga para a simulacao.", "success");
  } catch (error) {
    clearPreviewState();
    setStatusBanner(error.message || "Nao foi possivel consultar a base.", "error");
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
    setStatusBanner("Simulacao pronta. A area de proposta ja foi liberada.", "success");
  } catch (error) {
    state.simulationStatus = "error";
    setStatusBanner(error.message || "A simulacao nao foi concluida.", "error");
    showTechnicalDetails(error);
  }

  renderAll();
}

async function handleProposal() {
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
    setStatusBanner("Proposta emitida com sucesso. Se quiser, inicie uma nova proposta.", "success");
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
  setActiveNav("simulationSection");
  document.getElementById("simulationSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
  window.setTimeout(() => {
    dom.agreementSelect?.focus();
  }, 180);
}

function buildSimulationRequest() {
  return {
    environment: state.environment,
    agreementId: state.selections.agreementId,
    productId: state.selections.productId,
    saleModalityId: state.selections.saleModalityId,
    withdrawTypeId: state.selections.withdrawTypeId,
    clientName: dom.clientNameInput.value.trim(),
    clientDocument: sanitizeDigits(dom.clientDocumentInput.value),
    clientPhone: sanitizeDigits(dom.clientPhoneInput.value),
    benefitNumber: dom.benefitNumberInput.value.trim(),
    userPassword: dom.userPasswordInput.value.trim(),
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
  document.getElementById("resultsSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function restoreSidebarState() {
  const collapsed = localStorage.getItem("suite-consignado-sidebar-collapsed") === "true";
  setSidebarCollapsed(collapsed);
}

function toggleSidebar() {
  setSidebarCollapsed(!document.body.classList.contains("sidebar-collapsed"));
}

function setSidebarCollapsed(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", Boolean(collapsed));
  localStorage.setItem("suite-consignado-sidebar-collapsed", String(Boolean(collapsed)));
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
  try {
    return await callback();
  } finally {
    button.disabled = false;
    button.textContent = originalText;
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









