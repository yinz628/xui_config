function appendTemplateRow(templateId, tbodyId) {
  const template = document.getElementById(templateId);
  const tbody = document.getElementById(tbodyId);
  if (!template || !tbody) {
    return;
  }
  const fragment = template.content.cloneNode(true);
  tbody.appendChild(fragment);
}
