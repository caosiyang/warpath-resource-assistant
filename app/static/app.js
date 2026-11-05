function emptyOffer() {
  return {
    resource_id: "",
    resource_qty: "",
    discounted_currency_qty: "",
    discount_pct: "",
    min_vip_level: "",
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
