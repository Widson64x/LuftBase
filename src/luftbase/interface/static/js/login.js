(() => {
    'use strict';

    const root = document.documentElement;
    const backgroundLayers = [...document.querySelectorAll('[data-login-background]')];
    const backgroundUrls = Array.isArray(window.LUFT_LOGIN_BACKGROUNDS)
        ? window.LUFT_LOGIN_BACKGROUNDS.filter((url) => typeof url === 'string' && url.trim())
        : [];
    const dots = [...document.querySelectorAll('[data-login-dot]')];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    const rotationInterval = 8000;
    const loadedImages = new Map();
    let currentImageIndex = 0;
    let activeLayerIndex = 0;
    let transitionInProgress = false;
    let rotationTimer = null;

    if (backgroundUrls[0]) loadedImages.set(backgroundUrls[0], Promise.resolve(true));

    const preloadBackground = (url) => {
        if (!url) return Promise.resolve(false);
        if (loadedImages.has(url)) return loadedImages.get(url);

        const loading = new Promise((resolve) => {
            const image = new Image();
            image.onload = () => resolve(true);
            image.onerror = () => resolve(false);
            image.src = url;
        });
        loadedImages.set(url, loading);
        return loading;
    };

    const updateDots = () => {
        const activeDot = currentImageIndex % dots.length;
        dots.forEach((dot, index) => dot.classList.toggle('is-active', index === activeDot));
    };

    const scheduleRotation = () => {
        window.clearTimeout(rotationTimer);
        if (backgroundUrls.length < 2 || reduceMotion.matches || document.hidden) return;
        rotationTimer = window.setTimeout(() => showBackground(currentImageIndex + 1), rotationInterval);
    };

    const findNextBackground = async (startIndex) => {
        for (let offset = 0; offset < backgroundUrls.length; offset += 1) {
            const index = (startIndex + offset) % backgroundUrls.length;
            if (index === currentImageIndex && backgroundUrls.length > 1) continue;
            if (await preloadBackground(backgroundUrls[index])) {
                return { index, url: backgroundUrls[index] };
            }
        }
        return null;
    };

    const showBackground = async (nextIndex) => {
        if (transitionInProgress || backgroundLayers.length < 2 || backgroundUrls.length < 2) {
            scheduleRotation();
            return;
        }

        transitionInProgress = true;
        const nextBackground = await findNextBackground(nextIndex % backgroundUrls.length);
        if (!nextBackground) {
            transitionInProgress = false;
            scheduleRotation();
            return;
        }

        const outgoingLayer = backgroundLayers[activeLayerIndex];
        const incomingLayerIndex = (activeLayerIndex + 1) % backgroundLayers.length;
        const incomingLayer = backgroundLayers[incomingLayerIndex];
        incomingLayer.style.backgroundImage = `url("${nextBackground.url.replace(/"/g, '\\"')}")`;
        incomingLayer.classList.remove('was-active');
        void incomingLayer.offsetWidth;

        outgoingLayer.classList.add('was-active');
        outgoingLayer.classList.remove('is-active');
        incomingLayer.classList.add('is-active');

        currentImageIndex = nextBackground.index;
        activeLayerIndex = incomingLayerIndex;
        updateDots();

        window.setTimeout(() => {
            outgoingLayer.classList.remove('was-active');
            outgoingLayer.style.backgroundImage = '';
            transitionInProgress = false;
            void preloadBackground(backgroundUrls[(currentImageIndex + 1) % backgroundUrls.length]);
            scheduleRotation();
        }, 1900);
    };

    document.addEventListener('visibilitychange', scheduleRotation);
    reduceMotion.addEventListener?.('change', scheduleRotation);
    updateDots();
    if (backgroundUrls.length > 1) {
        void preloadBackground(backgroundUrls[1]);
    }
    scheduleRotation();

    if (!reduceMotion.matches && window.matchMedia('(pointer: fine)').matches) {
        let pointerFrame = null;
        window.addEventListener('pointermove', (event) => {
            if (pointerFrame) return;
            pointerFrame = window.requestAnimationFrame(() => {
                const x = ((event.clientX / window.innerWidth) - 0.5) * 24;
                const y = ((event.clientY / window.innerHeight) - 0.5) * 24;
                root.style.setProperty('--login-pointer-x', `${x.toFixed(2)}px`);
                root.style.setProperty('--login-pointer-y', `${y.toFixed(2)}px`);
                pointerFrame = null;
            });
        }, { passive: true });
    }

    const passwordInput = document.getElementById('senha');
    const passwordToggle = document.querySelector('[data-password-toggle]');
    if (passwordInput && passwordToggle) {
        passwordToggle.addEventListener('click', () => {
            const shouldShow = passwordInput.type === 'password';
            passwordInput.type = shouldShow ? 'text' : 'password';
            passwordToggle.setAttribute('aria-label', shouldShow ? 'Ocultar senha' : 'Exibir senha');
            passwordToggle.setAttribute('aria-pressed', String(shouldShow));

            const icon = passwordToggle.querySelector('i');
            if (icon) icon.className = shouldShow ? 'ph ph-eye-slash' : 'ph ph-eye';
            passwordInput.focus({ preventScroll: true });
        });
    }

    const loginForm = document.querySelector('[data-login-form]');
    const submitButton = document.querySelector('[data-login-submit]');
    if (loginForm && submitButton) {
        loginForm.addEventListener('submit', () => {
            if (!loginForm.checkValidity()) return;
            submitButton.classList.add('is-loading');
            submitButton.setAttribute('aria-busy', 'true');
        });

        window.addEventListener('pageshow', () => {
            submitButton.classList.remove('is-loading');
            submitButton.removeAttribute('aria-busy');
        });
    }

    // O Chrome preserva a rolagem ao alterar o zoom. No layout desktop não há
    // rolagem da página, então removemos qualquer posição residual do viewport.
    const loginShell = document.querySelector('.login-shell');
    const formPanel = document.querySelector('.login-form-panel');
    let resizeFrame = null;
    window.addEventListener('resize', () => {
        if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
        resizeFrame = window.requestAnimationFrame(() => {
            if (window.matchMedia('(min-width: 861px)').matches) {
                window.scrollTo(0, 0);
                if (loginShell) loginShell.scrollTop = 0;
                if (formPanel && formPanel.scrollHeight <= formPanel.clientHeight + 1) {
                    formPanel.scrollTop = 0;
                }
            }
            resizeFrame = null;
        });
    }, { passive: true });
})();
