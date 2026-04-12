function appendTemplateRow(templateId, tbodyId) {
  const template = document.getElementById(templateId);
  const tbody = document.getElementById(tbodyId);
  if (!template || !tbody) {
    return;
  }
  const fragment = template.content.cloneNode(true);
  tbody.appendChild(fragment);
}

function findRowIndex(button) {
  const row = button.closest("tr");
  const tbody = row && row.parentElement;
  if (!row || !tbody) {
    return -1;
  }
  return Array.from(tbody.children).indexOf(row);
}

document.addEventListener("click", (event) => {
  const target = event.target.closest("button");
  if (!target) {
    return;
  }

  if (target.classList.contains("js-remove-row")) {
    const row = target.closest("tr");
    if (row) {
      row.remove();
    }
    return;
  }

  if (
    target.classList.contains("js-source-check") ||
    target.classList.contains("js-group-builder-open")
  ) {
    const index = findRowIndex(target);
    if (index >= 0) {
      target.value = String(index);
    }
  }
});
