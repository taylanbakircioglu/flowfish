# 🐟 Flowfish Login Debugging Guide

## 📊 Mevcut Durum

### ✅ Backend API - Çalışıyor
```bash
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```
**Sonuç:** ✅ 200 OK - JWT token başarıyla döndürülüyor

### ✅ Frontend - Deploy Edildi
- **Image:** `flowfish/frontend:local`
- **Pod Status:** Running (2/2 replicas)
- **Base URL:** `window.location.origin` (production mode)

### ✅ Ingress - Yapılandırıldı
- `/api` → backend:8000
- `/` → frontend:3000

### 🔧 Son Yapılan Değişiklik
Frontend API client'ı production mode'da `window.location.origin` kullanacak şekilde güncellendi.
Bu sayede tüm API istekleri `http://localhost/api/v1/...` formatında gönderilecek.

## 🔍 Login Hatasını Kontrol Etme Adımları

### 1. **Hard Refresh Yapın** (Çok Önemli!)
```
macOS: Command + Shift + R
Windows: Ctrl + Shift + R
```

### 2. **Browser Console'u Açın**
```
macOS: Command + Option + I
Windows: F12
```

### 3. **Network Tab'ını İzleyin**
- Network tab'ına geçin
- "Preserve log" seçeneğini aktif edin
- Login formunu doldurun (admin / admin123)
- Submit butonuna basın

### 4. **Console ve Network'te Kontrol Edilecekler**

#### A. Network Request Detayları:
```
Request URL: http://localhost/api/v1/auth/login
Request Method: POST
Status Code: ? (kontrol edin)
```

**Olası Durumlar:**

**✅ Status: 200 OK**
- Login başarılı
- Response'da `access_token` olmalı
- Sorun: Token localStorage'a kaydedilmemiş olabilir
- Çözüm: Console'da `localStorage.getItem('flowfish_token')` kontrol edin

**❌ Status: 401 Unauthorized**
- Kullanıcı adı veya şifre yanlış
- Backend'de kullanıcı yok
- Çözüm: Admin kullanıcısını kontrol edelim (aşağıda)

**❌ Status: 404 Not Found**
- API endpoint bulunamadı
- Ingress routing hatası
- Çözüm: Ingress configuration kontrol edilmeli

**❌ Status: 500 Internal Server Error**
- Backend hatası
- Veritabanı bağlantı sorunu
- Çözüm: Backend loglarına bakılmalı

**❌ Status: (failed) net::ERR_CONNECTION_REFUSED**
- Backend çalışmıyor
- Ingress backend'e ulaşamıyor
- Çözüm: Backend pod'ları kontrol edilmeli

**❌ CORS Error**
- `Access-Control-Allow-Origin` hatası
- Backend CORS ayarları eksik
- Çözüm: Backend CORS middleware kontrol edilmeli

#### B. Console Hata Mesajları:
Şunlara benzer hatalar olabilir:
```
- "Network error. Please check your connection."
- "401: Unauthorized"
- "Invalid username or password"
- "CORS policy blocked"
```

### 5. **Request Payload'u Kontrol Edin**
Network tab'ında login request'ine tıklayın:
- **Headers** → Content-Type: application/json olmalı
- **Payload** → `{"username": "admin", "password": "admin123"}` olmalı
- **Preview/Response** → Hata mesajını görebilirsiniz

## 🛠️ Olası Sorunlar ve Çözümleri

### Sorun 1: "Network error. Please check your connection."
**Sebep:** Frontend backend'e ulaşamıyor

**Kontroller:**
```bash
# Backend pod'ları çalışıyor mu?
kubectl get pods -n flowfish -l app=backend

# Backend service var mı?
kubectl get svc -n flowfish backend

# Ingress düzgün mü?
kubectl get ingress -n flowfish
```

**Çözüm:**
```bash
# Backend pod'ları yeniden başlat
kubectl rollout restart -n flowfish deployment/backend
```

---

### Sorun 2: "401 Unauthorized" veya "Invalid credentials"
**Sebep:** Admin kullanıcısı veritabanında yok veya şifre yanlış

**Kontrol:**
```bash
# PostgreSQL'e bağlan ve admin kullanıcısını kontrol et
kubectl exec -it -n flowfish deployment/postgresql -- psql -U flowfish -d flowfish -c "SELECT id, username, email FROM users WHERE username='admin';"
```

**Beklenen Sonuç:**
```
 id | username |        email         
----+----------+----------------------
  1 | admin    | admin@flowfish.local
```

**Eğer admin kullanıcısı yoksa:**
```bash
# Admin kullanıcısı oluştur (şifre: admin123)
kubectl exec -it -n flowfish deployment/postgresql -- psql -U flowfish -d flowfish -c "
INSERT INTO users (username, email, password_hash, is_active, created_at, updated_at)
VALUES ('admin', 'admin@flowfish.local', '\$2b\$12\$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyE3H.oavjHu', true, NOW(), NOW())
ON CONFLICT (username) DO NOTHING;
"

# Admin rolü ver
kubectl exec -it -n flowfish deployment/postgresql -- psql -U flowfish -d flowfish -c "
INSERT INTO user_roles (user_id, role_id, created_at)
SELECT u.id, r.id, NOW()
FROM users u, roles r
WHERE u.username = 'admin' AND r.name = 'Super Admin'
ON CONFLICT DO NOTHING;
"
```

---

### Sorun 3: Browser Cache Sorunu
**Sebep:** Eski JavaScript dosyaları cache'de

**Çözümler:**
1. **Hard Refresh:** Command + Shift + R (macOS)
2. **Incognito Mode:** Command + Shift + N
3. **Clear Cache:**
   ```
   Developer Tools → Application → Clear Storage → Clear site data
   ```
4. **Force Reload:**
   ```
   Network tab → Disable cache checkbox'ını işaretle
   ```

---

### Sorun 4: CORS Hatası
**Sebep:** Backend CORS ayarları eksik

**Kontrol:**
```bash
# Backend response header'larını kontrol et
curl -I http://localhost/api/v1/health
```

**Beklenen Header'lar:**
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
```

**Eğer yoksa backend'i kontrol edin:**
```python
# backend/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

### Sorun 5: Yanlış API Endpoint
**Sebep:** Frontend yanlış URL'e istek gönderiyor

**Kontrol:**
```javascript
// Browser Console'da çalıştır:
console.log(axios.defaults.baseURL);

// veya localStorage'ı kontrol et
localStorage.clear(); // Test için temizle
```

**Beklenen:** `http://localhost` (production) veya `http://localhost:8000` (dev)

---

## 🧪 Manuel Test Komutları

### Test 1: Backend Health Check
```bash
curl http://localhost/api/v1/health
```
**Beklenen:** `{"status":"healthy","database":"connected",...}`

### Test 2: Login API (Doğrudan)
```bash
curl -X POST http://localhost/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' \
  | jq
```
**Beklenen:** `{"access_token": "eyJ...", "user": {...}}`

### Test 3: Frontend Erişimi
```bash
curl -I http://localhost/
```
**Beklenen:** `200 OK` + HTML content

### Test 4: API Proxy (Ingress)
```bash
curl http://localhost/api/v1/health
```
**Beklenen:** Backend'den response

### Test 5: Backend Logs
```bash
kubectl logs -n flowfish deployment/backend --tail=50 -f
```
Login denemesi yaptığınızda `POST /api/v1/auth/login` görmelisiniz.

### Test 6: Frontend Logs
```bash
kubectl logs -n flowfish deployment/frontend --tail=20
```
Nginx access log'larını görmelisiniz.

## 📋 Hızlı Checklist

- [ ] Browser'da hard refresh yapıldı (Cmd+Shift+R)
- [ ] Network tab açık ve istekler izleniyor
- [ ] Console'da hata mesajı var mı kontrol edildi
- [ ] Backend health check başarılı (`/api/v1/health`)
- [ ] Backend login API curl ile test edildi (başarılı)
- [ ] Admin kullanıcısı veritabanında mevcut
- [ ] Frontend pod'ları running durumunda
- [ ] Backend pod'ları running durumunda
- [ ] Ingress doğru yapılandırılmış

## 🎯 Şu Anda Durum

### ✅ Çalışan:
- Backend API
- PostgreSQL database
- Frontend deployment
- Ingress routing
- Ocean theme UI

### 🔄 Test Edilmesi Gereken:
- Browser'dan login denemesi
- Network request inspection
- Console error logs

## 📞 Sonraki Adımlar

1. **Browser'da http://localhost/login açın**
2. **Hard refresh yapın (Cmd+Shift+R)**
3. **Developer Console'u açın (Cmd+Option+I)**
4. **Network tab'ına geçin**
5. **Login deneyin: admin / admin123**
6. **Hata mesajını buraya bildirin:**
   - Network request status code?
   - Console error message?
   - Response body?

---

**Son Güncelleme:** 21 Kasım 2025  
**Durum:** ✅ Backend çalışıyor, Frontend deploy edildi, Login testi bekleniyor

