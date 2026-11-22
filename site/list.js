// The grocery list panel: offers added from the cards plus your own items, grouped per store.
(() => {
  "use strict";

  const STORE_NAMES = window.STORE_NAMES;
  const OWN_ITEMS = "Any shop"; // same wording as the shop picker's "no shop" option
  const user = window.userState;
  const dialog = document.getElementById("list-dialog");
  const items = document.getElementById("list-items");
  const count = document.getElementById("list-count");
  const eur = (n) => "€" + n.toFixed(2).replace(".", ",");

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function groupByStore(list) {
    const groups = new Map();
    for (const item of list) {
      const store = STORE_NAMES[item.store] || OWN_ITEMS;
      if (!groups.has(store)) groups.set(store, []);
      groups.get(store).push(item);
    }
    return groups;
  }

  function itemRow(item) {
    const li = el("li", "list-item" + (item.done ? " done" : ""));
    const check = el("label", "list-check");
    const box = el("input");
    box.type = "checkbox";
    box.checked = item.done;
    box.addEventListener("change", () => user.toggleItem(item.id));
    check.append(box, el("span", "list-text", item.text));
    if (item.detail) check.append(el("span", "small", item.detail));
    li.append(check);
    li.append(el("span", "list-price", item.price != null ? eur(item.price) : ""));
    const remove = el("button", "icon-btn");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${item.text}`);
    remove.title = "Remove";
    const removeIcon = el("span", "material-symbols-outlined", "close");
    removeIcon.setAttribute("aria-hidden", "true");
    remove.append(removeIcon);
    remove.addEventListener("click", () => user.removeItem(item.id));
    li.append(remove);
    return li;
  }

  function renderItems(list) {
    items.textContent = "";
    for (const [store, storeItems] of groupByStore(list)) {
      const section = el("li", "list-group");
      section.append(el("h3", null, store));
      const ul = el("ul");
      storeItems.forEach((item) => ul.append(itemRow(item)));
      section.append(ul);
      items.append(section);
    }
    document.getElementById("list-empty").hidden = list.length > 0;
  }

  // Shows what's still to buy: prices are per pack and only known for offers.
  function renderTotal(list) {
    const toBuy = list.filter((i) => !i.done && i.price != null);
    const total = toBuy.reduce((sum, i) => sum + i.price, 0);
    document.getElementById("list-total").textContent =
      toBuy.length ? `Still to buy: about ${eur(total)} for ${toBuy.length} offer(s)` : "";
  }

  function renderWhereSaved() {
    document.getElementById("list-saved").textContent = user.username
      ? `Saved to your account (${user.username}), on every device you sign in on.`
      : "Kept in this browser only. Sign in to save it to your account.";
  }

  function show({ saveError } = {}) {
    const list = user.list;
    const open = list.filter((i) => !i.done).length;
    count.textContent = open;
    count.hidden = open === 0;
    renderItems(list);
    renderTotal(list);
    renderWhereSaved();
    const message = document.getElementById("list-message");
    message.textContent = saveError ? `Couldn't save: ${saveError}` : "";
    message.classList.toggle("bad", Boolean(saveError));
  }

  function fillShopPicker(select) {
    for (const [store, name] of Object.entries(STORE_NAMES)) {
      const option = el("option", null, name);
      option.value = store;
      select.append(option);
    }
  }

  const addForm = document.getElementById("list-add");
  fillShopPicker(addForm.elements.store);
  addForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const input = addForm.elements.text; // not "item": forms already have an item() method
    const text = input.value.trim();
    if (!text) return;
    // The shop stays selected, so several items for one shop can be added in a row.
    const store = addForm.elements.store.value || undefined;
    user.addItem({ id: `own:${Date.now()}`, text, store });
    input.value = "";
    input.focus();
  });
  document.getElementById("list-clear").addEventListener("click", () => user.clearDone());
  document.getElementById("list-btn").addEventListener("click", () => dialog.showModal());
  dialog.querySelector(".dialog-close").addEventListener("click", () => dialog.close());

  user.subscribe(show);
  show();
})();
