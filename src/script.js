// Variables Globales
let config = {};
let autoskipConfig = {};
let appConfig = {};

// Initialisation
async function init() {
    // Récupération de la configuration initiale
    config = await eel.get_config()();
    autoskipConfig = await eel.get_autoskip_config()();
    appConfig = await eel.get_app_config()();
    
    // Mettre à jour l'UI avec la config
    updateUIFromConfig();
    updateAutoskipUIFromConfig();
    updateAppUIFromConfig();
    
    // Vérifier l'état du bot au démarrage
    checkBotStatus();
    // Polling du statut toutes les 2 secondes au cas où
    setInterval(checkBotStatus, 2000);
}

// ==========================================
// NAVIGATION (ACCORDION & TABS)
// ==========================================
const navCategories = document.querySelectorAll('.nav-category');
navCategories.forEach(cat => {
    cat.addEventListener('click', () => {
        const groupTarget = cat.getAttribute('data-group');
        if (!groupTarget) return; // Sécurité si on clique sur un titre non déroulant
        
        cat.classList.toggle('active');
        const icon = cat.querySelector('i');
        const group = document.getElementById(groupTarget);
        
        if (cat.classList.contains('active')) {
            group.style.display = 'block';
            if(icon) icon.classList.replace('ri-arrow-right-s-line', 'ri-arrow-down-s-line');
        } else {
            group.style.display = 'none';
            if(icon) icon.classList.replace('ri-arrow-down-s-line', 'ri-arrow-right-s-line');
        }
    });
});
const navItems = document.querySelectorAll('.nav-item');
const sections = document.querySelectorAll('.content-section');

navItems.forEach(item => {
    item.addEventListener('click', () => {
        // Enlever la classe active partout
        navItems.forEach(nav => nav.classList.remove('active'));
        sections.forEach(sec => sec.classList.remove('active'));
        
        // Ajouter active sur cliqué
        item.classList.add('active');
        const targetId = item.getAttribute('data-target');
        document.getElementById(targetId).classList.add('active');
    });
});

// ==========================================
// BOT CONTROL
// ==========================================
const btnToggleBot = document.getElementById('btn-toggle-bot');
const btnToggleText = document.getElementById('btn-toggle-text');
const iconPlay = document.querySelector('.icon-play');
const iconStop = document.querySelector('.icon-stop');
const statusDot = document.getElementById('bot-status-dot');
const statusText = document.getElementById('bot-status-text');

let isBotRunning = false;

async function checkBotStatus() {
    const status = await eel.get_bot_status()();
    updateBotUIStatus(status);
    
    const autoskipStatus = await eel.get_autoskip_status()();
    updateAutoskipUIStatus(autoskipStatus);
}

eel.expose(updateBotUIStatus);
function updateBotUIStatus(running) {
    isBotRunning = running;
    if (running) {
        btnToggleBot.classList.remove('start');
        btnToggleBot.classList.add('stop');
        btnToggleText.textContent = "Arrêter Autoplay";
        iconPlay.style.display = 'none';
        iconStop.style.display = 'inline-block';
        
        statusDot.classList.remove('offline');
        statusDot.classList.add('online');
        statusText.textContent = "Bot en exécution";
    } else {
        btnToggleBot.classList.remove('stop');
        btnToggleBot.classList.add('start');
        btnToggleText.textContent = "Démarrer Autoplay";
        iconPlay.style.display = 'inline-block';
        iconStop.style.display = 'none';
        
        statusDot.classList.remove('online');
        statusDot.classList.add('offline');
        statusText.textContent = "Bot arrêté";
    }
}

btnToggleBot.addEventListener('click', async () => {
    // Si le bot ne tourne pas, on vérifie qu'on a bien sauvegardé avant
    if (!isBotRunning) {
        const result = await eel.start_bot()();
        if (result.success) {
            showToast(result.message);
            updateBotUIStatus(true);
            updateAutoskipUIStatus(false); // Exclusivité
        } else {
            showToast("Erreur: " + result.message);
        }
    } else {
        const result = await eel.stop_bot()();
        if (result.success) {
            showToast(result.message);
            updateBotUIStatus(false);
        }
    }
});

// ==========================================
// AUTOSKIP CONTROL
// ==========================================
const btnToggleAutoskip = document.getElementById('btn-toggle-autoskip');
const btnToggleAutoskipText = document.getElementById('btn-toggle-autoskip-text');
const iconPlayAutoskip = document.querySelector('.icon-play-autoskip');
const iconStopAutoskip = document.querySelector('.icon-stop-autoskip');

let isAutoskipRunning = false;

eel.expose(updateAutoskipUIStatus);
function updateAutoskipUIStatus(running) {
    isAutoskipRunning = running;
    if (running) {
        btnToggleAutoskip.classList.remove('start');
        btnToggleAutoskip.classList.add('stop');
        btnToggleAutoskipText.textContent = "Arrêter Autoskip";
        iconPlayAutoskip.style.display = 'none';
        iconStopAutoskip.style.display = 'inline-block';
        
        statusDot.classList.remove('offline');
        statusDot.classList.add('online');
        statusText.textContent = "Autoskip en cours";
    } else {
        btnToggleAutoskip.classList.remove('stop');
        btnToggleAutoskip.classList.add('start');
        btnToggleAutoskipText.textContent = "Démarrer Autoskip";
        iconPlayAutoskip.style.display = 'inline-block';
        iconStopAutoskip.style.display = 'none';
        
        if (!isBotRunning) {
            statusDot.classList.remove('online');
            statusDot.classList.add('offline');
            statusText.textContent = "Arrêté";
        }
    }
}

btnToggleAutoskip.addEventListener('click', async () => {
    if (!isAutoskipRunning) {
        const result = await eel.start_autoskip()();
        if (result.success) {
            showToast(result.message);
            updateAutoskipUIStatus(true);
            updateBotUIStatus(false); // Exclusivité
        } else {
            showToast("Erreur: " + result.message);
        }
    } else {
        const result = await eel.stop_autoskip()();
        if (result.success) {
            showToast(result.message);
            updateAutoskipUIStatus(false);
        }
    }
});

function updateAutoskipUIFromConfig() {
    if (!autoskipConfig) return;
    if(autoskipConfig.skip_key) document.getElementById('autoskip_key').textContent = autoskipConfig.skip_key;
    if(autoskipConfig.interval_ms) document.getElementById('autoskip_interval').value = autoskipConfig.interval_ms;
}

const btnCaptureAutoskipKey = document.getElementById('btn-capture-autoskip-key');
btnCaptureAutoskipKey.addEventListener('click', async () => {
    captureOverlay.style.display = 'flex';
    const key = await eel.capture_key()();
    captureOverlay.style.display = 'none';
    
    if (key) {
        document.getElementById('autoskip_key').textContent = key;
        autoskipConfig.skip_key = key;
        await eel.save_autoskip_config(autoskipConfig)();
        showToast(`Touche Autoskip modifiée en ${key.toUpperCase()}`);
    }
});

const btnSaveAutoskip = document.getElementById('btn-save-autoskip');
btnSaveAutoskip.addEventListener('click', async () => {
    let interval = parseInt(document.getElementById('autoskip_interval').value);
    interval = Math.max(15, interval);
    document.getElementById('autoskip_interval').value = interval;
    autoskipConfig.interval_ms = interval;
    await eel.save_autoskip_config(autoskipConfig)();
    showToast("Configuration Autoskip sauvegardée");
});

// ==========================================
// GESTION DE CONFIGURATION
// ==========================================
function updateUIFromConfig() {
    if (!config) return;
    
    // Keys
    if (!config.keys || config.keys.length < 6) {
        config.keys = ['a','s','d','j','k','l'];
    }
    for (let i = 0; i < 6; i++) {
        const keyEl = document.getElementById(`key-${i}`);
        if(keyEl) keyEl.textContent = config.keys[i];
    }
    
    // Columns (absolu pour l'affichage)
    if (!config.columns_x || config.columns_x.length < 6) {
        config.columns_x = [10, 235, 451, 671, 884, 1099];
    }
    const x_start = config.x_start || 350;
    for (let i = 0; i < 6; i++) {
        const colEl = document.getElementById(`col-${i}`);
        if(colEl) colEl.value = x_start + config.columns_x[i];
    }
    
    // Geometry
    if(config.initial_y) document.getElementById('initial_y').value = config.initial_y;
    if(config.x_start) document.getElementById('x_start').value = config.x_start;
    if(config.x_end) document.getElementById('x_end').value = config.x_end;
    if(config.height) document.getElementById('height').value = config.height;
    
    // Advanced
    if(config.pixel_threshold) document.getElementById('pixel_threshold').value = config.pixel_threshold;
    if(config.tap_duration) document.getElementById('tap_duration').value = config.tap_duration;
    if(config.tap_cooldown) document.getElementById('tap_cooldown').value = config.tap_cooldown;
    if(config.hold_debounce) document.getElementById('hold_debounce').value = config.hold_debounce;
}

// ==========================================
// CALIBRATION CLAVIER
// ==========================================
const captureBtns = document.querySelectorAll('.btn-capture-key');
const captureOverlay = document.getElementById('capture-overlay');

captureBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
        const index = btn.getAttribute('data-index');
        
        // Afficher l'overlay
        captureOverlay.style.display = 'flex';
        
        // Appeler python pour bloquer et écouter la touche
        const key = await eel.capture_key()();
        
        // Cacher l'overlay
        captureOverlay.style.display = 'none';
        
        if (key) {
            // Mettre à jour l'UI
            document.getElementById(`key-${index}`).textContent = key;
            
            // Mettre à jour la config en local
            if (!config.keys) config.keys = ['a','s','d','j','k','l'];
            config.keys[index] = key;
            
            // Sauvegarder
            await eel.save_config(config)();
            showToast(`Touche ${key.toUpperCase()} assignée à la colonne ${parseInt(index)+1}`);
        }
    });
});

// ==========================================
// GEOMETRY & ADVANCED SETTINGS
// ==========================================
const btnSaveGeometry = document.getElementById('btn-save-geometry');
const btnSaveAdvanced = document.getElementById('btn-save-advanced');

btnSaveGeometry.addEventListener('click', async () => {
    config.initial_y = parseInt(document.getElementById('initial_y').value);
    config.x_start = parseInt(document.getElementById('x_start').value);
    config.x_end = parseInt(document.getElementById('x_end').value);
    config.height = parseInt(document.getElementById('height').value);
    
    await eel.save_config(config)();
    showToast("Dimensions sauvegardées");
});

btnSaveAdvanced.addEventListener('click', async () => {
    config.pixel_threshold = parseInt(document.getElementById('pixel_threshold').value);
    config.tap_duration = parseFloat(document.getElementById('tap_duration').value);
    config.tap_cooldown = parseFloat(document.getElementById('tap_cooldown').value);
    config.hold_debounce = parseFloat(document.getElementById('hold_debounce').value);
    
    await eel.save_config(config)();
    showToast("Paramètres avancés sauvegardés");
});

// ==========================================
// CAPTURE SOURIS (POSITIONS)
// ==========================================
const posCaptureBtns = document.querySelectorAll('.btn-capture-pos');
const clickOverlay = document.getElementById('click-overlay');

posCaptureBtns.forEach(btn => {
    btn.addEventListener('click', async () => {
        const targetId = btn.getAttribute('data-target'); // initial_y, x_start, ou x_end
        
        // Afficher overlay
        clickOverlay.style.display = 'flex';
        
        // Attendre le clic (Python)
        const pos = await eel.capture_click()();
        
        clickOverlay.style.display = 'none';
        
        if (pos) {
            const [x, y] = pos;
            if (targetId === 'initial_y') {
                document.getElementById('initial_y').value = y;
                showToast(`Hauteur Y capturée : ${y}`);
            } else if (targetId === 'x_start' || targetId === 'x_end') {
                document.getElementById(targetId).value = x;
                showToast(`Position X capturée : ${x}`);
            } else if (targetId.startsWith('col-')) {
                const index = parseInt(targetId.split('-')[1]);
                document.getElementById(targetId).value = x;
                const x_start = config.x_start || 350;
                config.columns_x[index] = x - x_start;
                await eel.save_config(config)();
                showToast(`Colonne ${index + 1} capturée : X=${x}`);
            }
        }
    });
});

// ==========================================
// APP SHORTCUTS CONFIGURATION
// ==========================================
const btnCaptureAppKey = document.querySelectorAll('.btn-capture-app-key');
btnCaptureAppKey.forEach(btn => {
    btn.addEventListener('click', async () => {
        const targetId = btn.getAttribute('data-target');
        
        captureOverlay.style.display = 'flex';
        const key = await eel.capture_key()();
        captureOverlay.style.display = 'none';
        
        if (key) {
            let pynputKey = key;
            if (key.length > 1 && !key.startsWith('<')) {
                pynputKey = `<${key}>`;
            }
            
            document.getElementById(targetId).textContent = pynputKey;
            appConfig[targetId] = pynputKey;
            await eel.save_and_reload_app_config(appConfig)();
            showToast(`Raccourci modifié en ${pynputKey}`);
        }
    });
});

function updateAppUIFromConfig() {
    if (!appConfig) return;
    if(appConfig.hotkey_music) document.getElementById('hotkey_music').textContent = appConfig.hotkey_music;
    if(appConfig.hotkey_skip) document.getElementById('hotkey_skip').textContent = appConfig.hotkey_skip;
}

// ==========================================
// UTILS
// ==========================================
function showToast(message) {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.classList.add('show');
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Start
init();
