(function () {
  const canvas = document.getElementById('login-canvas');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let width, height;
  let particles = [];
  let iconsReady = false;

  const ICONS = ['\uF2D6', '\uF4DA', '\uF4CF', '\uF3CD', '\uF56C', '\uF3EE', '\uF56B', '\uF1C0', '\uF2B9'];
  // laptop, shield-check, people, graph-up-arrow, tools, folder, key, database, gear
  const COLORS = ['#ffffff', '#FDBA74', '#7DD3FC', '#A5B4FC', '#86EFAC'];

  function resize() {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
  }

  class Particle {
    constructor() {
      this.reset();
    }

    reset() {
      this.x = Math.random() * width;
      this.y = Math.random() * height;
      this.vx = (Math.random() - 0.5) * 0.6;
      this.vy = (Math.random() - 0.5) * 0.6;
      this.radius = Math.random() * 4 + 2;
      this.color = COLORS[Math.floor(Math.random() * COLORS.length)];
      this.icon = ICONS[Math.floor(Math.random() * ICONS.length)];
      this.pulse = Math.random() * Math.PI * 2;
      this.pulseSpeed = 0.02 + Math.random() * 0.03;
      this.alpha = 0.4 + Math.random() * 0.5;
    }

    update() {
      this.x += this.vx;
      this.y += this.vy;
      this.pulse += this.pulseSpeed;

      if (this.x < -40) this.x = width + 40;
      if (this.x > width + 40) this.x = -40;
      if (this.y < -40) this.y = height + 40;
      if (this.y > height + 40) this.y = -40;
    }

    draw() {
      const pulseRadius = this.radius + Math.sin(this.pulse) * 1.5;

      // Outer glow
      const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, pulseRadius * 5);
      gradient.addColorStop(0, hexToRgba(this.color, 0.22));
      gradient.addColorStop(1, 'transparent');
      ctx.fillStyle = gradient;
      ctx.beginPath();
      ctx.arc(this.x, this.y, pulseRadius * 5, 0, Math.PI * 2);
      ctx.fill();

      // Core
      ctx.globalAlpha = this.alpha;
      ctx.fillStyle = this.color;
      ctx.beginPath();
      ctx.arc(this.x, this.y, pulseRadius, 0, Math.PI * 2);
      ctx.fill();
      ctx.globalAlpha = 1;

      // Icon
      if (iconsReady) {
        ctx.fillStyle = '#0f172a';
        ctx.font = `${Math.max(8, pulseRadius * 1.3)}px "bootstrap-icons"`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(this.icon, this.x, this.y);
      }
    }
  }

  function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function initParticles() {
    const count = Math.min(80, Math.floor((width * height) / 16000));
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push(new Particle());
    }
  }

  function drawConnections() {
    const maxDist = 150;
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < maxDist) {
          const opacity = (1 - dist / maxDist) * 0.25;
          ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(particles[i].x, particles[i].y);
          ctx.lineTo(particles[j].x, particles[j].y);
          ctx.stroke();
        }
      }
    }
  }

  function animate() {
    ctx.clearRect(0, 0, width, height);
    drawConnections();
    particles.forEach(p => {
      p.update();
      p.draw();
    });
    requestAnimationFrame(animate);
  }

  function waitForIcons() {
    return document.fonts.ready.then(() => {
      iconsReady = document.fonts.check('12px "bootstrap-icons"');
    }).catch(() => {
      iconsReady = false;
    });
  }

  window.addEventListener('resize', () => {
    resize();
    initParticles();
  });

  resize();
  initParticles();
  waitForIcons().then(animate);
})();
