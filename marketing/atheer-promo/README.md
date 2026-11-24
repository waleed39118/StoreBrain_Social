# Atheer promo video · فيديو أثير الترويجي

117-second, 1920×1080 bilingual (Arabic/English) promo video. Every reply, number and screenshot comes from the real program.

## Re-render · إعادة الإنتاج

Requires Node.js, Playwright (with Chromium) and ffmpeg.

```bash
npm install
npm run stills    # preview frames in stills/
npm run render    # writes atheer-promo.mp4 (~10 minutes)
```

- Edit text in `promo.html`; scene timings are in the `SCENES` array at the bottom.
- `assets/docs.png` is a real screenshot of Atheer's `/docs` page. Regenerate it with `node shot.js assets/docs.png` while `atheer-server` runs on port 8777 (Swagger UI files are served from the local `swagger-ui-dist` package).
- The closing scene has a generic call to action. Add contact details (phone, email, website) in the `#s11` section before sharing with buyers.
