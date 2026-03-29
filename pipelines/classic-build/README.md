# Flowfish Classic Build Pipeline - Incremental Build Support

Bu dizin Azure DevOps Classic (UI-based) Build Pipeline için task scriptlerini içerir.

## 🆕 Incremental Build Özelliği (v2.0)

Pipeline artık sadece **değişen servisleri** derliyor:
- Build süreleri **%70-80 oranında kısalıyor**
- Gereksiz image push'ları önleniyor
- Registry alanından tasarruf ediliyor

## Pipeline Yapısı

```
┌──────────────────────┐
│    DetectChanges     │  ← İlk çalışır (tek job)
│     (Agent Job)      │
└──────────┬───────────┘
           │
           ▼
┌──────────┴─────────────────────────────────────────┐
│               PARALLEL BUILDS                       │
│  ┌────────────┐  ┌────────────┐  ┌───────────────┐ │
│  │BuildBackend│  │BuildFrontend│  │BuildMicrosvcs│ │
│  │ (depends)  │  │ (depends)   │  │  (depends)   │ │
│  └────────────┘  └────────────┘  └───────────────┘ │
└────────────────────────┬───────────────────────────┘
                         │
                         ▼
                  ┌──────────┐
                  │  Cleanup │
                  │(depends) │
                  └──────────┘
```

## Dizin Yapısı

```
classic-build/
├── README.md                         # Bu dosya
├── detect-changes/
│   └── task.sh                       # Change detection task (ilk job)
├── build-backend/
│   └── task.sh                       # Backend build task
├── build-frontend/
│   └── task.sh                       # Frontend build task
├── build-microservices/
│   └── task.sh                       # Microservices build task
└── cleanup/
    └── task.sh                       # Cleanup task
```

---

# 🔧 PIPELINE KURULUM ADIMLARI

## Adım 1: Classic Build Pipeline Oluştur

1. Azure DevOps → **Pipelines** → **New Pipeline**
2. **Use the classic editor** tıklayın
3. Repository: `Flowfish`, Branch: `pilot`
4. Template: **Empty job** seçin
5. Pipeline name: `Flowfish-CI`

---

## Adım 2: Variable Groups Bağla

1. **Variables** tab'ına gidin
2. **Variable groups** → **Link variable group**
3. Şu grupları ekleyin:
   - `FlowfishVaultENV`
   - `FlowfishCompanyVariable`

---

## Adım 3: Pipeline Variables Ekle

**Variables** tab → **Pipeline variables**:

| Name | Value | Settable at queue time |
|------|-------|------------------------|
| `build-all` | `false` | ✅ Yes |
| `DEPLOYMENT_ENV` | `pilot` | ✅ Yes |
| `GADGET_VERSION` | `v0.48.0` | ✅ Yes |
| `cleanup-keep-count` | `4` | ✅ Yes |

> **GADGET_VERSION:** Inspektor Gadget OCI image'larını Harbor'a mirror etmek için kullanılır.
> Bu değer `services/ingestion-service/app/constants.py` ile uyumlu olmalıdır.
> **CVE-2024-24790 fix için v0.48.0 gereklidir.**
>
> **cleanup-keep-count:** Her servis için registry'de tutulacak image sayısı (latest hariç). Default: 4.

---

## Adım 4: Agent Jobs Oluştur

### 📌 JOB 1: DetectChanges (İLK JOB)

**Job Oluşturma:**
1. **Agent job** yanındaki **+** butonuna tıklayın
2. Yeni job oluşturun

**Job Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Detect Changes` |
| Agent pool | `BuildServers` |
| Allow scripts to access OAuth token | ✅ **İşaretli** |

**Task Ekleme:**
1. Job içinde **+** butonuna tıklayın
2. **Bash** task'ını arayın ve ekleyin

**Bash Task Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Detect Changes` |
| Type | `File Path` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/detect-changes/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

**⚠️ ÖNEMLİ - Reference Name:**
1. Task'ın sağ üst köşesindeki **...** menüsüne tıklayın
2. **View YAML** altında veya **Output Variables** bölümünde
3. **Reference name** alanına: `DetectChanges` yazın

> Bu reference name, diğer job'ların bu task'ın output variable'larına erişmesi için gerekli!

---

### 📌 JOB 2: BuildBackend

**Job Oluşturma:**
1. **Agent job** yanındaki **+** butonuna tıklayın

**Job Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Build Backend` |
| Agent pool | `BuildServers` |

**🔴 Dependencies Ayarı (ÖNEMLİ):**
1. Job'a tıklayın
2. Sağ panelde **Dependencies** bölümünü bulun
3. **+ Add** butonuna tıklayın
4. `Detect Changes` job'unu seçin

**Bash Task Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Build Backend` |
| Type | `File Path` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/build-backend/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

**Environment Variables** (Advanced bölümünde):
```
BACKEND_CHANGED=$(DetectChanges.DetectChanges.BACKEND_CHANGED)
BUILD_SOURCEVERSION=$(Build.SourceVersion)
```

---

### 📌 JOB 3: BuildFrontend

**Job Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Build Frontend` |
| Agent pool | `BuildServers` |
| Dependencies | `Detect Changes` |

**Bash Task Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Build Frontend` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/build-frontend/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

**Environment Variables:**
```
FRONTEND_CHANGED=$(DetectChanges.DetectChanges.FRONTEND_CHANGED)
BUILD_SOURCEVERSION=$(Build.SourceVersion)
```

---

### 📌 JOB 4: BuildMicroservices

**Job Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Build Microservices` |
| Agent pool | `BuildServers` |
| Dependencies | `Detect Changes` |

**Bash Task Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Build All Microservices` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/build-microservices/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

**Environment Variables:**
```
API_GATEWAY_CHANGED=$(DetectChanges.DetectChanges.API_GATEWAY_CHANGED)
CLUSTER_MANAGER_CHANGED=$(DetectChanges.DetectChanges.CLUSTER_MANAGER_CHANGED)
ANALYSIS_ORCHESTRATOR_CHANGED=$(DetectChanges.DetectChanges.ANALYSIS_ORCHESTRATOR_CHANGED)
GRAPH_WRITER_CHANGED=$(DetectChanges.DetectChanges.GRAPH_WRITER_CHANGED)
GRAPH_QUERY_CHANGED=$(DetectChanges.DetectChanges.GRAPH_QUERY_CHANGED)
TIMESERIES_WRITER_CHANGED=$(DetectChanges.DetectChanges.TIMESERIES_WRITER_CHANGED)
INGESTION_SERVICE_CHANGED=$(DetectChanges.DetectChanges.INGESTION_SERVICE_CHANGED)
BUILD_SOURCEVERSION=$(Build.SourceVersion)
GADGET_VERSION=$(GADGET_VERSION)
```

> **🆕 GADGET_VERSION:** Inspektor Gadget image'larını Harbor'a mirror etmek için gerekli.
> Pipeline Variables'a `GADGET_VERSION=v0.48.0` ekleyin (CVE-2024-24790 fix).

---

### 📌 JOB 5: Cleanup

**Job Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Cleanup` |
| Agent pool | `BuildServers` |
| Run this job | `Even if a previous task has failed, unless the build was canceled` |

**🔴 Dependencies Ayarı (ÖNEMLİ):**
1. Job'a tıklayın
2. **Dependencies** bölümünde **+ Add** 
3. Şu job'ları seçin:
   - ☑️ `Build Backend`
   - ☑️ `Build Frontend`
   - ☑️ `Build Microservices`

**Bash Task Ayarları:**
| Ayar | Değer |
|------|-------|
| Display name | `Safe Cleanup` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/cleanup/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

**Task 1: Detect Changes** (DetectChanges task'ını Cleanup'a da ekleyin)
| Ayar | Değer |
|------|-------|
| Display name | `Detect Changes` |
| Type | `File Path` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/detect-changes/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

> ⚠️ **Reference name** ayarlamaya gerek yok (aynı job içinde kullanılacak)

**Task 2: Safe Cleanup**
| Ayar | Değer |
|------|-------|
| Display name | `Safe Cleanup` |
| Type | `File Path` |
| Script Path | `$(Build.SourcesDirectory)/pipelines/classic-build/cleanup/task.sh` |
| Working Directory | `$(Build.SourcesDirectory)` |

> **Not:** DetectChanges task'ı aynı job içinde çalıştığı için `*_CHANGED` değişkenleri otomatik olarak cleanup task'ına aktarılır.
> **CLEANUP_KEEP_COUNT:** Pipeline variable olarak tanımlanırsa, registry'de kaç image tutulacağını belirler (default: 4, latest hariç).

---

## Adım 5: Pipeline'ı Kaydet ve Test Et

1. **Save & queue** butonuna tıklayın
2. İlk build'de tüm servisler derlenir (normal)
3. Sonraki build'lerde sadece değişenler derlenir

---

# 📋 ÖZET: Environment Variables Referans Tablosu

## DetectChanges Job → Build Jobs

| Build Job | Environment Variable | Değer |
|-----------|---------------------|-------|
| BuildBackend | `BACKEND_CHANGED` | `$(DetectChanges.DetectChanges.BACKEND_CHANGED)` |
| BuildFrontend | `FRONTEND_CHANGED` | `$(DetectChanges.DetectChanges.FRONTEND_CHANGED)` |
| BuildMicroservices | `API_GATEWAY_CHANGED` | `$(DetectChanges.DetectChanges.API_GATEWAY_CHANGED)` |
| BuildMicroservices | `CLUSTER_MANAGER_CHANGED` | `$(DetectChanges.DetectChanges.CLUSTER_MANAGER_CHANGED)` |
| BuildMicroservices | `ANALYSIS_ORCHESTRATOR_CHANGED` | `$(DetectChanges.DetectChanges.ANALYSIS_ORCHESTRATOR_CHANGED)` |
| BuildMicroservices | `GRAPH_WRITER_CHANGED` | `$(DetectChanges.DetectChanges.GRAPH_WRITER_CHANGED)` |
| BuildMicroservices | `GRAPH_QUERY_CHANGED` | `$(DetectChanges.DetectChanges.GRAPH_QUERY_CHANGED)` |
| BuildMicroservices | `TIMESERIES_WRITER_CHANGED` | `$(DetectChanges.DetectChanges.TIMESERIES_WRITER_CHANGED)` |
| BuildMicroservices | `INGESTION_SERVICE_CHANGED` | `$(DetectChanges.DetectChanges.INGESTION_SERVICE_CHANGED)` |

> **Format:** `$(JobName.TaskReferenceName.VARIABLE_NAME)`
> - JobName: `DetectChanges` (job display name, boşluksuz)
> - TaskReferenceName: `DetectChanges` (task'a verdiğiniz reference name)
> - VARIABLE_NAME: Script'in set ettiği değişken adı

---

# 🔍 Troubleshooting

## "Variable is empty" Hatası

**Sorun:** Build job'larında `*_CHANGED` değişkenleri boş geliyor.

**Çözümler:**
1. DetectChanges task'ının **Reference name** ayarlandı mı? → `DetectChanges`
2. Build job'larında **Dependencies** ayarlandı mı? → `Detect Changes`
3. Environment variable syntax'ı doğru mu? → `$(DetectChanges.DetectChanges.VAR_NAME)`

## "OAuth token" Hatası

**Sorun:** `⚠️ İlk build veya API erişimi yok` mesajı görünüyor.

**Çözüm:**
1. DetectChanges job → **Allow scripts to access the OAuth token** ✅

## Tüm Servisler Hala Derleniyor

**Sorun:** Değişiklik olmasa bile tüm servisler derleniyor.

**Kontrol:**
1. DetectChanges log'larını kontrol edin
2. `📌 Son başarılı build:` satırı görünüyor mu?
3. Değişken değerleri doğru set ediliyor mu?

---

# 🎯 Performance Karşılaştırması

| Senaryo | Eski Süre | Yeni Süre | Kazanım |
|---------|-----------|-----------|---------|
| Sadece frontend değişti | ~35 dk | ~7 dk | **%80** |
| Sadece 1 microservice değişti | ~35 dk | ~8 dk | **%77** |
| Sadece backend değişti | ~35 dk | ~8 dk | **%77** |
| Proto değişti (tüm servisler) | ~35 dk | ~35 dk | - |
| build-all=true | ~35 dk | ~35 dk | - |

---

# 🔄 Override Seçenekleri

## Tüm Servisleri Zorla Derleme

**Queue New Build** → **Variables**:
- `build-all` = `true`

Bu, tüm değişiklik kontrollerini bypass eder ve her şeyi derler.
Cleanup da otomatik olarak çalışır (çünkü en az bir değişiklik var).

## Tutulacak Image Sayısını Değiştirme

**Queue New Build** → **Variables**:
- `cleanup-keep-count` = `6`

Default değer 4'tür. Bu değer, registry'de her servis için kaç image tutulacağını belirler (latest hariç).
