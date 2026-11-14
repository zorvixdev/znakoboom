(() => {
  const CURRENCY = new Intl.NumberFormat("ru-RU");
  const EXPERIENCE = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 });
  const RARITIES = ["обычный", "необычный", "редкий", "эпический", "мифический", "легендарный"];
  const COUNTRIES = [
    { id: "ru", name: "Россия", flag: "🇷🇺" },
    { id: "kz", name: "Казахстан", flag: "🇰🇿" },
    { id: "by", name: "Беларусь", flag: "🇧🇾" },
  ];
  const DAILY_REWARDS = [30000, 50000, 80000, 120000, 200000, 300000, 1000000];
  const GENERATION_COST = 3000;
  const DAILY_ORDERS = [
    { id: "generate_5", title: "Первые находки", description: "Сгенерируй 5 номеров", target: 5, progress: "generated", reward: 15000 },
    { id: "generate_15", title: "На волне", description: "Сгенерируй 15 номеров", target: 15, progress: "generated", reward: 50000 },
    { id: "fuse_1", title: "Мастер переплавки", description: "Переплавь один номер", target: 1, progress: "fused", reward: 30000 },
  ];
  const PERKS = [
    { id: "lucky", name: "Нумеролог", icon: "🍀", title: "Чувствую удачу", short: "+20% шанс редкости", description: "+20% к шансу редких, мифических и легендарных номеров.", color: "green" },
    { id: "dealer", name: "Автодилер", icon: "💸", title: "Умею торговаться", short: "+15% к продаже", description: "+15% к выручке от быстрой продажи номеров.", color: "gold" },
    { id: "mechanic", name: "Механик", icon: "🔧", title: "Учусь на ходу", short: "+50% опыта", description: "+50% опыта за каждый сгенерированный номер.", color: "blue" },
    { id: "archivist", name: "Архивариус", icon: "🗄️", title: "Бережно храню", short: "+10 ячеек", description: "+10 мест в коллекции и +5 в сейфе.", color: "purple" },
  ];
  const UPGRADES = [
    { id: "generator", name: "Генератор", icon: "🧰", description: "Больше шансов на редкие комбинации.", base: 30000, factor: 1, max: 11 },
    { id: "storage", name: "Инвентарь", icon: "🗄️", description: "Каждый уровень добавляет 10 мест в коллекцию.", base: 50000, factor: 1.65, max: 11 },
    { id: "safe", name: "Сейф", icon: "🔐", description: "Каждый уровень добавляет 5 защищённых мест.", base: 75000, factor: 2.4, max: 11 },
    { id: "showcase", name: "Витрина", icon: "🏪", description: "Каждый уровень добавляет 2 выставочных места.", base: 100000, factor: 3.2, max: 6 },
  ];
  const MENU_ITEMS = [
    { id: "rewards", icon: "🎁", title: "Награды", subtitle: "Ежедневный бонус" },
    { id: "halloween", icon: "🎃", title: "Хэллоуин", subtitle: "Собирай тыквы" },
    { id: "friends", icon: "👥", title: "Пригласи друзей", subtitle: "Реферальная программа" },
    { id: "leaderboard", icon: "🏆", title: "Таблица лидеров", subtitle: "Соревнования игроков" },
    { id: "collection", icon: "🎫", title: "Коллекция", subtitle: "Твои номера" },
    { id: "safe", icon: "🔐", title: "Сейф", subtitle: "Защищённое хранение" },
    { id: "showcase", icon: "🏪", title: "Витрина", subtitle: "Номера на показ" },
    { id: "perks", icon: "✨", title: "Моя фишка", subtitle: "Персональный бонус" },
    { id: "orders", icon: "📋", title: "Заказы", subtitle: "Особые задания" },
    { id: "atlas", icon: "🗺️", title: "Атлас регионов", subtitle: "Собери регионы" },
    { id: "furnace", icon: "🔥", title: "Переплавка", subtitle: "Обмен редкостей" },
    { id: "catalog", icon: "✨", title: "Каталог редкостей", subtitle: "Все классы номеров" },
    { id: "stats", icon: "📊", title: "Статистика", subtitle: "Твой игровой путь" },
  ];
  const tg = window.Telegram && window.Telegram.WebApp;
  let state = null;
  let userProfile = null;
  let screen = "home";
  let rarityFilter = "все";
  let furnaceRarity = RARITIES[0];
  let selected = new Set();
  let recentNumber = null;
  let noticeTimer = null;
  let pending = false;
  let leaderboardData = null;
  let leaderboardLoading = false;
  let leaderboardError = "";

  if (tg) {
    tg.ready();
    tg.expand();
    if (tg.setHeaderColor) tg.setHeaderColor("#101113");
    if (tg.setBackgroundColor) tg.setBackgroundColor("#0e0f11");
  }

  const root = document.querySelector("#screen");
  const money = (value) => `${CURRENCY.format(Math.round(value || 0))} ₽`;
  const esc = (value) => String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
  const country = (id) => COUNTRIES.find((item) => item.id === id) || COUNTRIES[0];
  const today = () => new Date().toISOString().slice(0, 10);
  const apiHeaders = () => ({
    "Content-Type": "application/json",
    Authorization: tg && tg.initData ? `tma ${tg.initData}` : "",
  });

  function showNotice(text, isError = false) {
    const notice = document.querySelector("#notice");
    notice.textContent = text;
    notice.hidden = false;
    notice.classList.toggle("error", isError);
    clearTimeout(noticeTimer);
    noticeTimer = setTimeout(() => {
      notice.hidden = true;
    }, 3000);
    if (tg && tg.HapticFeedback) {
      if (isError) tg.HapticFeedback.notificationOccurred("error");
      else tg.HapticFeedback.impactOccurred("light");
    }
  }

  function confirmSale(count) {
    if (!tg || !tg.showPopup) return Promise.resolve(window.confirm(`Продать ${count} номеров по их коллекционной стоимости?`));
    return new Promise((resolve) => {
      tg.showPopup({
        title: "Продать номера?",
        message: `${count} выбранных номеров будут проданы за их коллекционную стоимость.`,
        buttons: [
          { id: "sell", text: "Продать", type: "destructive" },
          { type: "cancel" },
        ],
      }, (buttonId) => resolve(buttonId === "sell"));
    });
  }

  async function refreshState() {
    try {
      const response = await fetch("/api/state", { headers: apiHeaders() });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Не удалось загрузить игру");
      state = result.state;
      userProfile = result.user;
      document.querySelector("#balance").textContent = CURRENCY.format(state.balance);
      updateEventWallet();
      render();
    } catch (error) {
      root.innerHTML = `<div class="empty-state"><strong>Не получилось подключиться</strong><br>${esc(error.message)}<br><br><button class="secondary-button" data-action="retry">Попробовать ещё раз</button></div>`;
      document.querySelector("#balance").textContent = "—";
    }
  }

  async function act(action, details = {}) {
    if (pending) return null;
    pending = true;
    root.querySelectorAll("button, select, input").forEach((button) => {
      button.disabled = true;
    });
    try {
      const response = await fetch("/api/action", {
        method: "POST",
        headers: apiHeaders(),
        body: JSON.stringify({ action, ...details }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Не удалось выполнить действие");
      state = result.state;
      if (result.generated) recentNumber = result.generated;
      selected.clear();
      document.querySelector("#balance").textContent = CURRENCY.format(state.balance);
      updateEventWallet();
      if (action !== "event_activity" || result.pumpkinsEarned || screen === "halloween") render();
      if (result.generated) {
        const pumpkinNotice = result.pumpkinsEarned ? " · 🎃 Нашёл тыкву!" : "";
        showNotice(`${result.generated.rarity[0].toUpperCase()}${result.generated.rarity.slice(1)} номер · ${money(result.generated.price)}${pumpkinNotice}`);
        if (["легендарный", "мифический"].includes(result.generated.rarity)) {
          if (tg && tg.HapticFeedback) tg.HapticFeedback.notificationOccurred("success");
        }
      } else if (result.reward) {
        showNotice(result.pumpkinsEarned ? `🎁 Бонус ${money(result.reward)} и ${result.pumpkinsEarned} 🎃` : `Ежедневный бонус: ${money(result.reward)}`);
      } else if (action === "claim_event_daily") {
        showNotice(`За вход получено ${result.pumpkinsEarned} 🎃`);
      } else if (action === "event_activity" && result.pumpkinsEarned) {
        showNotice(`За время в игре: +${result.pumpkinsEarned} 🎃`);
      } else if (result.earned) {
        showNotice(`Продано за ${money(result.earned)}`);
      } else if (result.fused) {
        recentNumber = result.fused;
        showNotice(`Переплавка! Новый ${result.fused.rarity} номер · плата ${money(result.fee)}`);
        screen = "furnace";
      } else if (result.frameClaimed) {
        showNotice("Эксклюзивная хэллоуинская рамка получена!");
      } else if (result.orderReward) {
        showNotice(`Задание выполнено: +${money(result.orderReward)}`);
      } else if (action === "upgrade") {
        showNotice("Улучшение куплено");
      } else if (action === "safe" || action === "showcase") {
        showNotice(action === "safe" ? "Сейф обновлён" : "Витрина обновлена");
      }
      return result;
    } catch (error) {
      showNotice(error.message, true);
      return null;
    } finally {
      pending = false;
      render();
    }
  }

  function topbar(title, eyebrow = "ТВОЯ КОЛЛЕКЦИЯ") {
    document.querySelector("#screen-title").textContent = title;
    document.querySelector("#screen-title").classList.toggle("brand-title", title === "Знакобум");
    document.querySelector(".eyebrow").textContent = eyebrow;
  }

  function updateEventWallet() {
    const wallet = document.querySelector("#pumpkin-wallet");
    wallet.hidden = !state || !state.halloween || !state.halloween.active;
    document.querySelector("#pumpkins").textContent = state && state.halloween ? state.halloween.pumpkins : 0;
  }

  function levelProgress() {
    let floor = 0;
    for (let level = 1; level < state.level; level += 1) floor += 10 + level * 4;
    const target = 10 + state.level * 4;
    return {
      current: Math.max(0, state.experience - floor),
      target,
      percent: Math.min(100, Math.max(0, ((state.experience - floor) / target) * 100)),
    };
  }

  function plateMarkup(number) {
    const info = country(number.country);
    const parts = String(number.plate).split(" ");
    const lettersAndDigits = esc(parts[0] || number.plate);
    const region = esc(number.regionCode || parts[1] || "");
    return `<span class="plate" role="img" aria-label="${esc(info.name)} номер ${esc(number.plate)}"><span class="plate-flag">${info.flag}</span><span class="plate-main">${lettersAndDigits}</span><span class="plate-region"><strong>${region}</strong><small>${esc(number.suffix || info.id.toUpperCase())}</small></span></span>`;
  }

  function home() {
    topbar("Знакобум", "ТВОЯ КОЛЛЕКЦИЯ");
    const progress = levelProgress();
    const newest = recentNumber || [...state.numbers].sort((a, b) => b.createdAt - a.createdAt)[0] || {
      plate: "А777АА 777",
      country: "ru",
      regionCode: "777",
      suffix: "RUS",
    };
    const rewardClaimed = state.lastDaily === today();
    return `
      <section class="hero">
        <div class="level-row">
          <div class="level-badge">${state.level}</div>
          <div class="level-copy">
            <strong>Автолюбитель <span class="level-caption">УР. ${state.level}</span></strong>
            <span>${EXPERIENCE.format(progress.current)} / ${EXPERIENCE.format(progress.target)} опыта</span>
            <div class="progress-track"><div class="progress-fill" style="width:${progress.percent}%"></div></div>
          </div>
        </div>
      </section>
      <section class="generator-card">
        <div class="generator-caption"><span>ГЕНЕРАТОР</span><span class="rarity ${esc(newest.rarityColor || "rare")}">${esc(newest.rarity || `УР. ${state.upgrades.generator}`)}</span></div>
        <button class="generator-plate-tap ${state.halloween.exclusiveFrame ? "pumpkin-frame" : ""}" data-action="tap" aria-label="Нажми на автомобильный номер, чтобы сгенерировать новый" ${state.balance < GENERATION_COST || state.numbers.length >= state.inventoryCapacity ? "disabled" : ""}>
          ${plateMarkup(newest)}
          <span class="tap-hint">👆 Нажми на номер</span>
        </button>
        <span class="generator-subtitle">${newest.region ? `Регион ${esc(newest.regionCode)}: ${esc(newest.region)}.` : "Новый номер ждёт!"} · ${money(GENERATION_COST)} за попытку</span>
      </section>
      <div class="country-select-row">
        <label for="tap-country">Страна</label>
        <select id="tap-country" class="game-select" data-select-country aria-label="Страна номера">
          ${COUNTRIES.map((item) => `<option value="${item.id}" ${state.country === item.id ? "selected" : ""}>${item.flag} ${item.name}</option>`).join("")}
        </select>
        <label for="tap-region">Регион</label>
        <select id="tap-region" class="game-select region-select" data-select-region aria-label="Регион номера">
          <option value="any" ${state.region === "any" ? "selected" : ""}>🗺️ Любой регион</option>
          ${state.regions.map((item) => `<option value="${esc(item.code)}" ${state.region === item.code ? "selected" : ""}>${esc(item.code)} · ${esc(item.name)}</option>`).join("")}
        </select>
      </div>
      ${recentNumber ? `<div class="recent-result">${plateMarkup(recentNumber)}<div class="recent-copy"><span>${esc(recentNumber.region)} · ${esc(recentNumber.rarity)}</span><strong>${money(recentNumber.price)}</strong></div></div>` : ""}
      ${state.halloween.active ? `<button class="event-banner" data-screen="halloween"><span class="event-banner-pumpkin">🎃</span><span class="event-banner-copy"><strong>Хэллоуин · ${state.halloween.pumpkins} тыкв</strong><small>Эксклюзивная рамка за ${state.halloween.pumpkinGoal} тыкв</small></span><span class="event-banner-go">В ивент →</span></button>` : ""}
      <button class="daily-banner ${rewardClaimed ? "claimed" : ""}" data-action="${rewardClaimed ? "screen-rewards" : "claim_daily"}">
        <span class="daily-gift">🎁</span><span class="daily-copy"><strong>${rewardClaimed ? "Бонус уже получен" : `Ежедневный бонус · ${money(DAILY_REWARDS[state.dailyStreak % DAILY_REWARDS.length])}`}</strong><small>${rewardClaimed ? "Новая награда будет завтра" : "Зайди сегодня и забери награду"}</small></span><span class="daily-arrow">${rewardClaimed ? "✓" : "Забрать"}</span>
      </button>
      <div class="section-heading compact-heading"><h2>Твоя фишка</h2><button data-screen="perks">${state.perk ? "Подробнее →" : "Выбрать →"}</button></div>
      ${perkSummary()}
      <div class="section-heading compact-heading"><h2>Быстрый доступ</h2><button data-screen="stats">Статистика →</button></div>
      <div class="menu-grid home-grid">
        <button class="menu-tile" data-screen="collection"><span class="menu-icon">🎫</span><strong>Коллекция</strong><span>${state.numbers.length} / ${state.inventoryCapacity} номеров</span></button>
        <button class="menu-tile" data-screen="upgrades"><span class="menu-icon">⬆️</span><strong>Улучшения</strong><span>Развивай генератор</span></button>
        <button class="menu-tile" data-screen="safe"><span class="menu-icon">🔐</span><strong>Сейф</strong><span>${state.numbers.filter((number) => number.inSafe).length} / ${state.safeCapacity} номеров</span></button>
        <button class="menu-tile" data-screen="showcase"><span class="menu-icon">🏪</span><strong>Витрина</strong><span>${state.numbers.filter((number) => number.onShowcase).length} / ${state.showcaseCapacity} номеров</span></button>
      </div>`;
  }

  function perkSummary() {
    const perk = PERKS.find((item) => item.id === state.perk);
    if (!perk) {
      return `<button class="perk-prompt" data-screen="perks"><span class="perk-prompt-icon">✨</span><span><strong>Выбери свой стиль игры</strong><small>Один из 4 постоянных бонусов — на твой выбор</small></span><span class="perk-arrow">→</span></button>`;
    }
    return `<button class="perk-summary ${perk.color}" data-screen="perks"><span class="perk-summary-icon">${perk.icon}</span><span><strong>${perk.name}</strong><small>${perk.title} · ${perk.short}</small></span><span class="perk-active">АКТИВНО</span></button>`;
  }

  function perks() {
    topbar("Моя фишка", "ТВОЙ ЛИЧНЫЙ БОНУС");
    const chosen = PERKS.find((perk) => perk.id === state.perk);
    return `
      <section class="perk-intro">
        <span class="perk-intro-icon">✨</span>
        <h2>${chosen ? "Твоя игра — твои правила" : "Выбери свою специализацию"}</h2>
        <p>${chosen ? `Ты выбрал специализацию «${chosen.name}». Она навсегда закреплена за твоим профилем и даёт постоянный бонус.` : "Это личный постоянный бонус. Подумай, что тебе ближе: редкости, торговля, опыт или большая коллекция. Выбор останется в твоём профиле."}</p>
      </section>
      <div class="perk-list">
        ${PERKS.map((perk) => {
          const isChosen = state.perk === perk.id;
          const unavailable = Boolean(state.perk) && !isChosen;
          return `
            <article class="perk-card ${perk.color} ${isChosen ? "chosen" : ""} ${unavailable ? "unavailable" : ""}">
              <div class="perk-card-icon">${perk.icon}</div>
              <div class="perk-card-body">
                <div class="perk-card-title"><h2>${perk.name}</h2>${isChosen ? '<span class="perk-stamp">ТВОЯ</span>' : ""}</div>
                <p>${perk.description}</p>
              </div>
              ${isChosen ? '<span class="perk-check">✓</span>' : unavailable ? '<span class="perk-lock">🔒</span>' : `<button class="perk-choose" data-action="choose_perk" data-perk="${perk.id}">Выбрать</button>`}
            </article>`;
        }).join("")}
      </div>
      <p class="perk-footnote">Специализацию можно выбрать только один раз. Другие постоянные улучшения по-прежнему доступны на экране «Улучшения».</p>`;
  }

  function numberCard(number) {
    const isSelected = selected.has(number.id);
    const labels = [];
    if (number.inSafe) labels.push("🔐 в сейфе");
    if (number.onShowcase) labels.push("🏪 на витрине");
    return `
      <article class="number-card ${isSelected ? "selected" : ""}">
        <div class="number-card-top">
          <span class="rarity ${esc(number.rarityColor)}">${esc(number.rarity)}</span>
          <label aria-label="Выбрать номер"><input class="selection-check" type="checkbox" data-select="${esc(number.id)}" ${isSelected ? "checked" : ""}></label>
        </div>
        ${plateMarkup(number)}
        <div class="number-details"><span>${esc(number.region)}${labels.length ? ` · ${labels.join(" · ")}` : ""}</span><strong class="number-price">${money(number.price)}</strong></div>
      </article>`;
  }

  function selectionActions(kind, values) {
    if (!values.length) return "";
    if (kind === "safe") {
      return `<div class="button-row"><button class="secondary-button" data-action="select-all">${values.length === selected.size ? "Снять выбор" : "Выбрать всё"}</button><button class="secondary-button" data-action="safe">🔐 ${values.every((number) => number.inSafe) ? "Достать из сейфа" : "В сейф"}</button></div>`;
    }
    if (kind === "showcase") {
      return `<div class="button-row"><button class="secondary-button" data-action="select-all">${values.length === selected.size ? "Снять выбор" : "Выбрать всё"}</button><button class="secondary-button" data-action="showcase">${values.every((number) => number.onShowcase) ? "Снять с витрины" : "На витрину"}</button></div>`;
    }
    return `<div class="button-row"><button class="secondary-button" data-action="select-all">${values.length === selected.size ? "Снять выбор" : "Выбрать всё"}</button><button class="secondary-button danger" data-action="sell">Продать выбранные</button></div>`;
  }

  function collection(kind = "collection") {
    const filtered = state.numbers.filter((number) => {
      if (kind === "safe") return number.inSafe;
      if (kind === "showcase") return number.onShowcase;
      return true;
    });
    const shown = rarityFilter === "все" ? filtered : filtered.filter((number) => number.rarity === rarityFilter);
    const totalValue = filtered.reduce((sum, number) => sum + number.price, 0);
    topbar(kind === "safe" ? "Сейф" : kind === "showcase" ? "Витрина" : "Коллекция", "СОБИРАЙ РЕДКОСТИ");
    const filters = kind === "collection" ? `
      <div class="filter-row">
        ${["все", ...RARITIES].map((rarity) => `<button class="filter-chip ${rarityFilter === rarity ? "active" : ""}" data-filter="${rarity}">${rarity === "все" ? "Все номера" : rarity}</button>`).join("")}
      </div>` : "";
    const heading = kind === "safe"
      ? `Защищённые номера · ${filtered.length} / ${state.safeCapacity}`
      : kind === "showcase"
        ? `На витрине · ${filtered.length} / ${state.showcaseCapacity}`
        : `${state.numbers.length} / ${state.inventoryCapacity} номеров · ${money(totalValue)}`;
    const intro = kind === "safe"
      ? "Номера из сейфа защищены от быстрой продажи. Выбери номер, чтобы достать его."
      : kind === "showcase"
        ? "Выстави любимые номера в витрину. Снятые с витрины номера снова появятся в коллекции."
        : "Выбирай фильтр редкости, отмечай номера и отправляй ценные комбинации в сейф.";
    return `
      <p class="screen-intro">${esc(heading)}<br>${intro}</p>
      ${filters}
      ${shown.length ? `<div class="number-list">${shown.map(numberCard).join("")}</div>` : `<div class="empty-state">${kind === "safe" ? "Сейф пока пуст.<br>Выбери номер в коллекции и нажми «В сейф»." : kind === "showcase" ? "Витрина ждёт первые номера.<br>Выбери номер и выстави его на витрину." : "Здесь пока нет номеров.<br>Нажми «Сгенерировать номер», чтобы начать коллекцию."}</div>`}
      ${selectionActions(kind, shown)}`;
  }

  function furnace() {
    const rank = RARITIES.indexOf(furnaceRarity);
    const nextRarity = RARITIES[rank + 1];
    const matching = state.numbers.filter((number) => number.rarity === furnaceRarity);
    const available = matching.filter((number) => !number.inSafe);
    const chosen = matching.filter((number) => selected.has(number.id));
    const fee = chosen.length === 5
      ? Math.max(1000, Math.floor(chosen.reduce((sum, number) => sum + number.price, 0) / 10))
      : 0;
    topbar("Переплавка", "ПЯТЬ НОМЕРОВ → ОДИН");
    return `
      <section class="furnace-intro">
        <span class="furnace-icon">🔥</span>
        <h2>Собери новую редкость</h2>
        <p>Выбери <strong>5 номеров одной редкости</strong>. Они превратятся в один случайный номер на ступень выше. Номера в сейфе переплавлять нельзя.</p>
        <div class="furnace-recipe"><span>${esc(furnaceRarity)}</span><b>× 5</b><i>→</i><strong>${nextRarity ? esc(nextRarity) : "максимум"}</strong></div>
      </section>
      <div class="filter-row furnace-filters">
        ${RARITIES.slice(0, -1).map((rarity) => `<button class="filter-chip ${furnaceRarity === rarity ? "active" : ""}" data-fuse-filter="${rarity}">${rarity} <small>${state.numbers.filter((number) => number.rarity === rarity && !number.inSafe).length}</small></button>`).join("")}
      </div>
      ${nextRarity ? `<div class="furnace-summary"><span>Можно переплавить: <strong>${available.length}</strong></span><span>Выбрано: <strong>${chosen.length} / 5</strong></span></div>` : `<div class="empty-state">Легендарный — максимальная редкость. Выше переплавлять некуда.</div>`}
      ${nextRarity && available.length ? `<div class="number-list">${available.map(numberCard).join("")}</div>` : nextRarity ? `<div class="empty-state">Нужно собрать пять номеров редкости «${esc(furnaceRarity)}» и вынуть их из сейфа.</div>` : ""}
      ${nextRarity && chosen.length === 5 ? `<div class="furnace-action"><span>Плата за плавку <strong>${money(fee)}</strong></span><button class="primary-button" data-action="fuse" ${state.balance < fee ? "disabled" : ""}>🔥 Переплавить 5 номеров</button></div>` : ""}
      ${nextRarity && available.length ? `<div class="button-row"><button class="secondary-button" data-action="select-all">${chosen.length === 5 ? "Снять выбор" : "Выбрать 5 номеров"}</button><span class="furnace-hint">Отметь ровно 5 одинаковой редкости</span></div>` : ""}`;
  }

  function halloween() {
    topbar("Хэллоуин", "СОБИРАЙ ТЫКВЫ");
    const event = state.halloween;
    const end = new Date(event.endsAt);
    const remainingDays = Math.max(0, Math.ceil((end.getTime() - Date.now()) / 86400000));
    const loginClaimed = event.dailyBonusDay === today();
    const canClaimFrame = event.pumpkins >= event.pumpkinGoal && !event.exclusiveFrame;
    const progress = Math.min(100, Math.round(event.pumpkins / event.pumpkinGoal * 100));
    return `
      <section class="halloween-hero">
        <div class="halloween-glow"></div>
        <div class="halloween-head"><span class="halloween-art">🎃</span><span class="halloween-title"><strong>Хэллоуин 2026</strong><small>${remainingDays} дн. до конца события</small></span><span class="halloween-total"><strong>${CURRENCY.format(event.pumpkins)}</strong><small>тыкв</small></span></div>
        <p>Нажимай на номера в генераторе и собирай тыквы. Чем больше играешь, тем ближе эксклюзивная рамка для твоей коллекции.</p>
        <div class="pumpkin-progress-label"><span>Эксклюзивная рамка</span><strong>${event.exclusiveFrame ? "ПОЛУЧЕНА" : `${event.pumpkins} / ${event.pumpkinGoal} 🎃`}</strong></div>
        <div class="pumpkin-progress"><span style="width:${event.exclusiveFrame ? 100 : progress}%"></span></div>
      </section>
      <div class="pumpkin-sources">
        <article><span>🎰</span><strong>${event.generatorToday} / 10</strong><small>Из генератора сегодня</small></article>
        <article><span>🌙</span><strong>${loginClaimed ? "5 / 5" : "0 / 5"}</strong><small>Ежедневный вход</small></article>
        <article><span>⏱️</span><strong>${event.activeToday} / 4</strong><small>За активную игру</small></article>
      </div>
      <section class="halloween-card">
        <h2>Как добывать тыквы</h2>
        <div class="pumpkin-rule"><span>🎃</span><span><strong>Крути генератор</strong><small>22% шанс за номер · максимум 10 в день</small></span></div>
        <div class="pumpkin-rule"><span>🎁</span><span><strong>Заходи каждый день</strong><small>Забирай бонус события в один тап: +5 тыкв</small></span></div>
        <div class="pumpkin-rule"><span>👻</span><span><strong>Оставайся в игре</strong><small>Каждые 15 активных минут · до 4 тыкв в день</small></span></div>
        <button class="halloween-claim" data-action="claim_event_daily" ${loginClaimed ? "disabled" : ""}>${loginClaimed ? "Ежедневные тыквы уже получены" : "Забрать ежедневные +5 🎃"}</button>
      </section>
      <section class="pumpkin-prize ${event.exclusiveFrame ? "unlocked" : ""}">
        <span class="prize-icon">${event.exclusiveFrame ? "🏆" : "🎁"}</span><span><strong>${event.exclusiveFrame ? "Эксклюзивная рамка твоя!" : "Награда события"}</strong><small>Неповторимая хэллоуинская рамка номера</small></span>
        <button class="prize-button" data-action="claim_halloween_frame" ${event.exclusiveFrame || !canClaimFrame ? "disabled" : ""}>${event.exclusiveFrame ? "Получена" : canClaimFrame ? "Забрать" : `${event.pumpkinGoal} 🎃`}</button>
      </section>`;
  }

  function upgradePrice(upgrade, level) {
    return Math.round(upgrade.base * upgrade.factor * (1.72 ** (level - 1)));
  }

  function upgrades() {
    topbar("Улучшения", "РАЗВИВАЙСЯ");
    return `
      <p class="screen-intro">Вместимость, редкость и возможности коллекции — каждый уровень открывает новые бонусы.</p>
      ${UPGRADES.map((item) => {
        const level = state.upgrades[item.id];
        const price = upgradePrice(item, level);
        const filled = Math.min(level, item.max);
        return `
          <article class="upgrade-card">
            <div class="upgrade-heading"><h2>${item.icon} ${item.name}</h2><span>Уровень ${level} / ${item.max}</span></div>
            <div class="upgrade-description">${item.description}</div>
            <div class="upgrade-track">${Array.from({ length: item.max }, (_, index) => `<span class="upgrade-segment ${index < filled ? "filled" : ""}"></span>`).join("")}</div>
            <div class="upgrade-meta">${item.id === "storage" ? `Занято ${state.numbers.length} из ${state.inventoryCapacity} ячеек` : item.id === "safe" ? `${state.numbers.filter((number) => number.inSafe).length} из ${state.safeCapacity} ячеек занято` : item.id === "showcase" ? `${state.numbers.filter((number) => number.onShowcase).length} из ${state.showcaseCapacity} мест занято` : "Следующий уровень увеличит шанс редкости"}</div>
            <button class="primary-button" data-action="upgrade" data-kind="${item.id}" ${level >= item.max || state.balance < price ? "disabled" : ""}>${level >= item.max ? "Максимальный уровень" : `Улучшить за ${money(price)}`}</button>
          </article>`;
      }).join("")}`;
  }

  function rewards() {
    topbar("Награды", "ЕЖЕДНЕВНЫЙ ПРОГРЕСС");
    const claimed = state.lastDaily === today();
    const streak = Math.max(0, state.dailyStreak);
    const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
    const nextDay = claimed ? streak : state.lastDaily === yesterday ? streak + 1 : 1;
    return `
      <section class="daily-card">
        <h2>🎁 Серия входов</h2>
        <p>${claimed ? `Награда получена. Твоя серия — ${streak} дн.` : "Заглядывай каждый день: награда становится больше!"}</p>
        <div class="reward-strip">${DAILY_REWARDS.map((reward, index) => `<div class="reward-day ${index + 1 === ((nextDay - 1) % 7) + 1 ? "today" : ""}"><span>День ${index + 1}</span><strong>${CURRENCY.format(reward)}</strong></div>`).join("")}</div>
        <button class="primary-button" data-action="claim_daily" ${claimed ? "disabled" : ""}>${claimed ? "Уже забрано сегодня" : `Забрать ${money(DAILY_REWARDS[(nextDay - 1) % 7])}`}</button>
      </section>
      <div class="section-heading"><h2>Задания дня</h2></div>
      <div class="feature-card"><p>Выполнено: ${state.dailyOrders.claimed.length} из ${DAILY_ORDERS.length}. Новые задания появляются каждый день по времени UTC.</p><button class="secondary-button" data-screen="orders">Перейти к заказам</button></div>`;
  }

  function stats() {
    topbar("Статистика", "ТВОЙ ИГРОВОЙ ПУТЬ");
    const mostValuable = [...state.numbers].sort((a, b) => b.price - a.price)[0];
    const countByRarity = Object.fromEntries(RARITIES.map((rarity) => [rarity, state.numbers.filter((number) => number.rarity === rarity).length]));
    const metrics = [
      ["Сгенерировано", CURRENCY.format(state.totalGenerated)],
      ["Потрачено", money(state.totalSpent)],
      ["Заработано", money(state.totalEarned)],
      ["Номеров в коллекции", CURRENCY.format(state.numbers.length)],
      ["Стоимость коллекции", money(state.numbers.reduce((sum, number) => sum + number.price, 0))],
      ...RARITIES.map((rarity) => [rarity[0].toUpperCase() + rarity.slice(1), CURRENCY.format(countByRarity[rarity])]),
    ];
    return `
      ${mostValuable ? `<section class="stats-highlight"><span>Самый дорогой номер</span>${plateMarkup(mostValuable)}<strong>${money(mostValuable.price)}</strong></section>` : `<div class="empty-state">Сгенерируй первый номер — и статистика коллекции появится здесь.</div>`}
      <div class="stats-list">${metrics.map(([label, value]) => `<div class="stats-row"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join("")}</div>`;
  }

  function orders() {
    topbar("Заказы", "ЗАДАНИЯ НА СЕГОДНЯ");
    const progress = state.dailyOrders;
    return `
      <p class="screen-intro">Выполняй задания в игре, забирай награды и возвращайся за новыми заказами после полуночи UTC.</p>
      <div class="order-list">${DAILY_ORDERS.map((order) => {
        const current = Math.min(progress[order.progress], order.target);
        const claimed = progress.claimed.includes(order.id);
        const complete = current >= order.target;
        return `<article class="order-card ${claimed ? "claimed" : ""}">
          <div class="order-heading"><span class="order-icon">${order.id === "fuse_1" ? "🔥" : "🎯"}</span><div><strong>${order.title}</strong><small>${order.description}</small></div></div>
          <div class="order-progress"><span style="width:${Math.round(current / order.target * 100)}%"></span></div>
          <div class="order-footer"><span>${current} / ${order.target} · ${money(order.reward)}</span>
            <button class="secondary-button" data-action="claim_order" data-order="${order.id}" ${!complete || claimed ? "disabled" : ""}>${claimed ? "Получено" : complete ? "Забрать" : "В процессе"}</button>
          </div>
        </article>`;
      }).join("")}</div>`;
  }

  function atlas() {
    topbar("Атлас регионов", "СОБЕРИ КАЖДЫЙ КРАЙ");
    const regions = state.regionCatalog || {};
    const collected = new Set(state.numbers.map((number) => `${number.country}:${number.regionCode}`));
    const total = Object.values(regions).reduce((sum, values) => sum + values.length, 0);
    return `
      <section class="atlas-summary"><strong>${collected.size} / ${total}</strong><span>регионов открыто</span><div class="order-progress"><span style="width:${total ? collected.size / total * 100 : 0}%"></span></div></section>
      ${Object.entries(regions).map(([countryId, values]) => {
        const info = country(countryId);
        const found = values.filter((region) => collected.has(`${countryId}:${region.code}`)).length;
        return `<section class="atlas-country"><div class="atlas-country-heading"><h2>${info.flag} ${info.name}</h2><span>${found} / ${values.length}</span></div>
          <div class="atlas-regions">${values.map((region) => {
            const isCollected = collected.has(`${countryId}:${region.code}`);
            const count = state.numbers.filter((number) => number.country === countryId && number.regionCode === region.code).length;
            return `<button class="atlas-region ${isCollected ? "collected" : ""}" data-action="atlas-region" data-country="${countryId}" data-region="${esc(region.code)}"><strong>${esc(region.code)}</strong><span>${esc(region.name)}</span><small>${isCollected ? `${count} номер${count === 1 ? "" : count < 5 ? "а" : "ов"}` : "Не найден"}</small></button>`;
          }).join("")}</div></section>`;
      }).join("")}
      <p class="atlas-hint">Нажми на регион, чтобы выбрать его в генераторе. Собранные номера остаются в коллекции и продолжают засчитываться.</p>`;
  }

  function friends() {
    topbar("Пригласи друзей", "ИГРАЙТЕ ВМЕСТЕ");
    const inviteUrl = userProfile && userProfile.referralUrl;
    const friendCount = userProfile ? userProfile.referralCount : 0;
    return `
      <section class="friends-card"><span class="friends-icon">👥</span><h2>Приглашай и получай награду</h2>
        <p>Ты и каждый друг получите по ${money(50000)} после того, как он впервые откроет игру по твоей ссылке.</p>
        <div class="friends-count"><strong>${friendCount}</strong><span>друзей уже присоединились</span></div>
        ${inviteUrl ? `<button class="primary-button" data-action="share-referral">Пригласить друга</button>` : `<div class="empty-state">Ссылка появится после настройки BOT_USERNAME в файле .env. Это имя бота без символа @.</div>`}
      </section>`;
  }

  function loadLeaderboard() {
    if (leaderboardLoading) return;
    leaderboardLoading = true;
    leaderboardError = "";
    fetch("/api/leaderboard", { headers: apiHeaders() })
      .then(async (response) => {
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Не удалось загрузить таблицу лидеров");
        leaderboardData = result.players;
      })
      .catch((error) => {
        leaderboardError = error.message;
      })
      .finally(() => {
        leaderboardLoading = false;
        if (screen === "leaderboard") render();
      });
  }

  function leaderboard() {
    topbar("Таблица лидеров", "СОРЕВНУЙСЯ С ИГРОКАМИ");
    if (!leaderboardData && !leaderboardError) {
      loadLeaderboard();
      return `<div class="empty-state">Загружаем рейтинг…</div>`;
    }
    if (leaderboardError) {
      return `<div class="empty-state">${esc(leaderboardError)}<br><br><button class="secondary-button" data-action="retry-leaderboard">Попробовать ещё раз</button></div>`;
    }
    if (!leaderboardData.length) return `<div class="empty-state">Рейтинг пока пуст. Сгенерируй первый номер!</div>`;
    return `<p class="screen-intro">Игроки ранжированы по накопленному опыту. При равенстве учитываются легендарные номера и размер коллекции.</p>
      <div class="leaderboard-list">${leaderboardData.map((player) => `<article class="leaderboard-row">
        <span class="leaderboard-rank">${player.rank <= 3 ? ["🥇", "🥈", "🥉"][player.rank - 1] : `#${player.rank}`}</span>
        <div class="leaderboard-player"><strong>${esc(player.name)}</strong><small>Ур. ${player.level} · ${EXPERIENCE.format(player.experience)} опыта</small></div>
        <span class="leaderboard-score">${player.legendaryCount} 🏆<small>${player.numberCount} ном.</small></span>
      </article>`).join("")}</div>`;
  }

  function catalog() {
    topbar("Каталог редкостей", "ИЗУЧАЙ КОМБИНАЦИИ");
    const chances = ["81,5%", "12%", "4,5%", "1,5%", "0,45%", "0,05%"];
    const samples = ["А124УУ 74", "В966ВА 59", "М777ММ 777", "А001АА 01", "Х777ХХ 99", "У000УУ 77"];
    return `<p class="screen-intro">Шансы — базовые. Улучшения генератора повышают вероятность редких комбинаций.</p>
      ${RARITIES.map((rarity, index) => `<article class="upgrade-card"><div class="upgrade-heading"><h2 class="rarity ${["common", "uncommon", "rare", "epic", "mythic", "legendary"][index]}">${rarity[0].toUpperCase() + rarity.slice(1)}</h2><span>шанс ${chances[index]}</span></div><strong>${money([300, 4000, 36000, 320000, 2000000, 15000000][index])} — ${money([4500, 36000, 320000, 2000000, 12000000, 50000000][index])}</strong><div style="margin-top:12px">${plateMarkup({ plate: samples[index], country: "ru", regionCode: "77", suffix: "RUS" })}</div></article>`).join("")}`;
  }

  function menu() {
    topbar("Меню", "ТВОЯ ИГРА");
    return `
      <section class="hero"><div class="level-row"><div class="level-badge">${state.level}</div><div class="level-copy"><strong>Автолюбитель <span class="level-caption">УР. ${state.level}</span></strong><span>Уровень ${state.level} · ${EXPERIENCE.format(state.experience)} опыта</span></div></div>
      <div class="progress-track"><div class="progress-fill" style="width:${levelProgress().percent}%"></div></div></section>
      <div class="menu-grid">${MENU_ITEMS.map((item) => `<button class="menu-tile" data-screen="${item.id}"><span class="menu-icon">${item.icon}</span><strong>${item.title}</strong><span>${item.subtitle}</span></button>`).join("")}</div>`;
  }

  function render() {
    if (!state) return;
    document.querySelectorAll(".nav-button").forEach((button) => {
      const active =
        (button.dataset.screen === "home" && screen === "home") ||
        (button.dataset.screen === "collection" && ["collection", "safe", "showcase"].includes(screen)) ||
        (button.dataset.screen === "upgrades" && screen === "upgrades") ||
        (button.dataset.screen === "menu" && !["home", "collection", "safe", "showcase", "upgrades"].includes(screen));
      button.classList.toggle("active", active);
    });
    const templates = {
      home,
      menu,
      collection: () => collection("collection"),
      safe: () => collection("safe"),
      showcase: () => collection("showcase"),
      halloween,
      furnace,
      upgrades,
      perks,
      rewards,
      orders,
      atlas,
      friends,
      leaderboard,
      stats,
      catalog,
    };
    root.innerHTML = templates[screen] ? templates[screen]() : menu();
  }

  document.addEventListener("click", async (event) => {
    const target = event.target.closest("button");
    if (!target || target.disabled) return;
    if (target.dataset.screen) {
      screen = target.dataset.screen;
      selected.clear();
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
      return;
    }
    if (target.dataset.filter) {
      rarityFilter = target.dataset.filter;
      selected.clear();
      render();
      return;
    }
    if (target.dataset.fuseFilter) {
      furnaceRarity = target.dataset.fuseFilter;
      selected.clear();
      render();
      return;
    }
    const action = target.dataset.action;
    if (!action) return;
    if (action === "retry") {
      await refreshState();
      return;
    }
    if (action === "screen-rewards") {
      screen = "rewards";
      render();
      return;
    }
    if (action === "retry-leaderboard") {
      leaderboardData = null;
      leaderboardError = "";
      render();
      return;
    }
    if (action === "claim_order") {
      await act(action, { orderId: target.dataset.order });
      return;
    }
    if (action === "atlas-region") {
      const result = await act("region", { country: target.dataset.country, region: target.dataset.region });
      if (result) {
        screen = "home";
        render();
        showNotice(`Выбран регион ${target.dataset.region}.`);
      }
      return;
    }
    if (action === "share-referral") {
      const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(userProfile.referralUrl)}&text=${encodeURIComponent("Заходи в Знакобум — собирай редкие автомобильные номера!")}`;
      if (tg && tg.openTelegramLink) tg.openTelegramLink(shareUrl);
      else window.open(shareUrl, "_blank", "noopener");
      return;
    }
    if (action === "country") {
      await act("country", { country: target.dataset.country });
      return;
    }
    if (action === "tap") {
      await act("tap", { country: state.country, region: state.region });
      return;
    }
    if (action === "select-all") {
      const visible = [...root.querySelectorAll("[data-select]")].map((input) => input.dataset.select);
      if (screen === "furnace") {
        const five = visible.slice(0, 5);
        if (five.length === 5 && five.every((id) => selected.has(id))) {
          five.forEach((id) => selected.delete(id));
        } else {
          selected.clear();
          five.forEach((id) => selected.add(id));
        }
      } else if (visible.length && visible.every((id) => selected.has(id))) {
        visible.forEach((id) => selected.delete(id));
      } else {
        visible.forEach((id) => selected.add(id));
      }
      render();
      return;
    }
    if (action === "sell") {
      if (!selected.size) {
        showNotice("Сначала выбери номера", true);
        return;
      }
      const protectedNumber = [...selected].some((id) => {
        const number = state.numbers.find((item) => item.id === id);
        return number && number.inSafe;
      });
      if (protectedNumber) {
        showNotice("Достань выбранные номера из сейфа", true);
        return;
      }
      if (!(await confirmSale(selected.size))) return;
      await act("sell", { ids: [...selected] });
      return;
    }
    if (action === "safe" || action === "showcase") {
      if (!selected.size) {
        showNotice("Сначала выбери номера", true);
        return;
      }
      await act(action, { ids: [...selected] });
      return;
    }
    if (action === "upgrade") {
      await act(action, { kind: target.dataset.kind });
      return;
    }
    if (action === "choose_perk") {
      const result = await act(action, { perk: target.dataset.perk });
      if (result) showNotice(`Твоя специализация: ${PERKS.find((perk) => perk.id === result.state.perk).name}`);
      return;
    }
    if (action === "fuse") {
      if (selected.size !== 5) {
        showNotice("Для переплавки выбери ровно пять номеров", true);
        return;
      }
      const chosen = state.numbers.filter((number) => selected.has(number.id));
      if (chosen.some((number) => number.rarity !== furnaceRarity || number.inSafe)) {
        showNotice("Выбери пять номеров одной редкости вне сейфа", true);
        return;
      }
      await act("fuse", { ids: [...selected] });
      return;
    }
    await act(action);
  });

  document.addEventListener("change", (event) => {
    const countrySelect = event.target.closest("[data-select-country]");
    if (countrySelect) {
      act("country", { country: countrySelect.value });
      return;
    }
    const regionSelect = event.target.closest("[data-select-region]");
    if (regionSelect) {
      act("region", { country: state.country, region: regionSelect.value });
      return;
    }
    const input = event.target.closest("[data-select]");
    if (!input) return;
    if (input.checked && screen === "furnace" && selected.size >= 5) {
      input.checked = false;
      showNotice("Для переплавки можно выбрать только 5 номеров", true);
      return;
    }
    if (input.checked) selected.add(input.dataset.select);
    else selected.delete(input.dataset.select);
    const card = input.closest(".number-card");
    if (card) card.classList.toggle("selected", input.checked);
  });

  document.querySelector(".bottom-nav").addEventListener("click", (event) => {
    const button = event.target.closest("[data-screen]");
    if (!button) return;
    screen = button.dataset.screen;
    selected.clear();
    render();
    window.scrollTo({ top: 0, behavior: "smooth" });
  });

  function startEventHeartbeat() {
    const ping = () => {
      if (state && state.halloween.active && document.visibilityState === "visible" && !pending) {
        act("event_activity");
      }
    };
    setInterval(ping, 60000);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") ping();
    });
  }

  refreshState().then(startEventHeartbeat);
})();
