function emptyOffer() {
  return {
    resource_id: "",
    resource_qty: "",
    list_currency_qty: "",
    discount_pct: "",
    limit_qty: "",
  };
}

function offerForm(initial) {
  return {
    rows: Array.isArray(initial) && initial.length ? initial : [emptyOffer()],
    addRow() {
      this.rows.push(emptyOffer());
    },
  };
}

function emptyBoxItem() {
  return {
    resource_id: "",
    qty: "",
    probability: "",
  };
}

function boxForm(initial) {
  return {
    rows: Array.isArray(initial) && initial.length ? initial : [emptyBoxItem()],
    addRow() {
      this.rows.push(emptyBoxItem());
    },
  };
}
