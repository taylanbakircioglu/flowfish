/**
 * InsightEngine - Akıllı Analiz Motoru
 * 
 * ML modeli kullanmadan, istatistiksel ve kural tabanlı akıllı analizler yapar:
 * - Anomaly Detection (Z-score, IQR)
 * - Trend Analysis (moving average, velocity)
 * - Correlation Detection (metrikler arası ilişki)
 * - Pattern Recognition (zaman bazlı pattern'ler)
 * - Root Cause Analysis (dependency graph)
 * - Predictive Alerts (trend-based prediction)
 */

// ============================================================================
// TYPES
// ============================================================================

export interface MetricDataPoint {
  timestamp: number;
  value: number;
}

export interface MetricSeries {
  name: string;
  data: MetricDataPoint[];
  metadata?: Record<string, any>;
}

export interface AnomalyResult {
  isAnomaly: boolean;
  score: number; // 0-1, 1 = kesinlikle anomaly
  direction: 'high' | 'low' | 'normal';
  expectedValue: number;
  actualValue: number;
  deviation: number; // kaç standart sapma
  method: 'zscore' | 'iqr' | 'mad' | 'percentile';
}

export interface TrendResult {
  direction: 'increasing' | 'decreasing' | 'stable' | 'volatile';
  velocity: number; // birim zamandaki değişim
  acceleration: number; // değişimin değişimi
  confidence: number; // 0-1
  prediction: {
    nextValue: number;
    nextHour: number;
    confidence: number;
  };
}

export interface CorrelationResult {
  metric1: string;
  metric2: string;
  coefficient: number; // -1 to 1
  strength: 'strong' | 'moderate' | 'weak' | 'none';
  direction: 'positive' | 'negative' | 'none';
  lagMinutes: number; // metric2'nin metric1'i ne kadar gecikmeyle takip ettiği
  causality: 'likely' | 'possible' | 'unlikely';
}

export interface PatternResult {
  type: 'spike' | 'dip' | 'plateau' | 'oscillation' | 'step_change' | 'gradual_drift';
  startTime: number;
  endTime?: number;
  magnitude: number;
  frequency?: number; // oscillation için
  isRecurring: boolean;
  recurringPattern?: 'hourly' | 'daily' | 'weekly';
}

export interface RootCauseCandidate {
  metric: string;
  probability: number; // 0-1
  evidence: string[];
  suggestedAction: string;
  relatedMetrics: string[];
}

export interface SmartInsight {
  id: string;
  type: 'anomaly' | 'trend' | 'correlation' | 'pattern' | 'prediction' | 'root_cause' | 'recommendation';
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  confidence: number; // 0-1
  title: string;
  description: string;
  technicalDetail?: string;
  metric?: string;
  value?: number | string;
  trend?: TrendResult;
  anomaly?: AnomalyResult;
  correlation?: CorrelationResult;
  pattern?: PatternResult;
  rootCause?: RootCauseCandidate[];
  suggestedActions: string[];
  relatedInsights?: string[];
  expiresAt?: number; // timestamp - bu insight ne zaman geçersiz olur
  tags: string[];
}

export interface InsightEngineConfig {
  anomalyThreshold: number; // Z-score threshold, default 2.5
  trendWindowSize: number; // kaç veri noktası, default 10
  correlationMinStrength: number; // minimum correlation coefficient, default 0.5
  patternMinDuration: number; // minimum pattern süresi (ms), default 5 dakika
  predictionHorizon: number; // kaç dakika ileri tahmin, default 60
  enabledAnalyses: {
    anomaly: boolean;
    trend: boolean;
    correlation: boolean;
    pattern: boolean;
    prediction: boolean;
    rootCause: boolean;
  };
}

// ============================================================================
// STATISTICAL UTILITIES
// ============================================================================

class StatUtils {
  /**
   * Ortalama hesapla
   */
  static mean(values: number[]): number {
    if (values.length === 0) return 0;
    return values.reduce((sum, v) => sum + v, 0) / values.length;
  }

  /**
   * Standart sapma hesapla
   */
  static stdDev(values: number[]): number {
    if (values.length < 2) return 0;
    const avg = this.mean(values);
    const squareDiffs = values.map(v => Math.pow(v - avg, 2));
    return Math.sqrt(this.mean(squareDiffs));
  }

  /**
   * Median hesapla
   */
  static median(values: number[]): number {
    if (values.length === 0) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  }

  /**
   * Percentile hesapla
   */
  static percentile(values: number[], p: number): number {
    if (values.length === 0) return 0;
    const sorted = [...values].sort((a, b) => a - b);
    const index = (p / 100) * (sorted.length - 1);
    const lower = Math.floor(index);
    const upper = Math.ceil(index);
    if (lower === upper) return sorted[lower];
    return sorted[lower] + (sorted[upper] - sorted[lower]) * (index - lower);
  }

  /**
   * IQR (Interquartile Range) hesapla
   */
  static iqr(values: number[]): { q1: number; q3: number; iqr: number; lowerBound: number; upperBound: number } {
    const q1 = this.percentile(values, 25);
    const q3 = this.percentile(values, 75);
    const iqr = q3 - q1;
    return {
      q1,
      q3,
      iqr,
      lowerBound: q1 - 1.5 * iqr,
      upperBound: q3 + 1.5 * iqr,
    };
  }

  /**
   * MAD (Median Absolute Deviation) hesapla
   */
  static mad(values: number[]): number {
    const med = this.median(values);
    const deviations = values.map(v => Math.abs(v - med));
    return this.median(deviations);
  }

  /**
   * Z-score hesapla
   */
  static zScore(value: number, mean: number, stdDev: number): number {
    if (stdDev === 0) return 0;
    return (value - mean) / stdDev;
  }

  /**
   * Pearson Correlation Coefficient hesapla
   */
  static correlation(x: number[], y: number[]): number {
    if (x.length !== y.length || x.length < 2) return 0;
    
    const n = x.length;
    const meanX = this.mean(x);
    const meanY = this.mean(y);
    
    let numerator = 0;
    let denomX = 0;
    let denomY = 0;
    
    for (let i = 0; i < n; i++) {
      const dx = x[i] - meanX;
      const dy = y[i] - meanY;
      numerator += dx * dy;
      denomX += dx * dx;
      denomY += dy * dy;
    }
    
    const denominator = Math.sqrt(denomX * denomY);
    if (denominator === 0) return 0;
    
    return numerator / denominator;
  }

  /**
   * Linear regression (slope ve intercept)
   */
  static linearRegression(x: number[], y: number[]): { slope: number; intercept: number; r2: number } {
    if (x.length !== y.length || x.length < 2) {
      return { slope: 0, intercept: 0, r2: 0 };
    }
    
    const n = x.length;
    const meanX = this.mean(x);
    const meanY = this.mean(y);
    
    let numerator = 0;
    let denominator = 0;
    
    for (let i = 0; i < n; i++) {
      numerator += (x[i] - meanX) * (y[i] - meanY);
      denominator += (x[i] - meanX) ** 2;
    }
    
    const slope = denominator !== 0 ? numerator / denominator : 0;
    const intercept = meanY - slope * meanX;
    
    // R² hesapla
    const predictions = x.map(xi => slope * xi + intercept);
    const ssRes = y.reduce((sum, yi, i) => sum + (yi - predictions[i]) ** 2, 0);
    const ssTot = y.reduce((sum, yi) => sum + (yi - meanY) ** 2, 0);
    const r2 = ssTot !== 0 ? 1 - ssRes / ssTot : 0;
    
    return { slope, intercept, r2 };
  }

  /**
   * Moving Average hesapla
   */
  static movingAverage(values: number[], windowSize: number): number[] {
    if (values.length < windowSize) return values;
    
    const result: number[] = [];
    for (let i = 0; i <= values.length - windowSize; i++) {
      const window = values.slice(i, i + windowSize);
      result.push(this.mean(window));
    }
    return result;
  }

  /**
   * Exponential Moving Average hesapla
   */
  static ema(values: number[], alpha: number = 0.3): number[] {
    if (values.length === 0) return [];
    
    const result: number[] = [values[0]];
    for (let i = 1; i < values.length; i++) {
      result.push(alpha * values[i] + (1 - alpha) * result[i - 1]);
    }
    return result;
  }

  /**
   * Değişim hızı (velocity) hesapla
   */
  static velocity(values: number[], timestamps: number[]): number {
    if (values.length < 2) return 0;
    
    const regression = this.linearRegression(timestamps, values);
    return regression.slope;
  }

  /**
   * Değişimin değişimi (acceleration) hesapla
   */
  static acceleration(values: number[], timestamps: number[]): number {
    if (values.length < 3) return 0;
    
    // İlk türev (velocity) hesapla
    const velocities: number[] = [];
    const velTimestamps: number[] = [];
    
    for (let i = 1; i < values.length; i++) {
      const dt = timestamps[i] - timestamps[i - 1];
      if (dt > 0) {
        velocities.push((values[i] - values[i - 1]) / dt);
        velTimestamps.push((timestamps[i] + timestamps[i - 1]) / 2);
      }
    }
    
    if (velocities.length < 2) return 0;
    
    // İkinci türev (acceleration)
    const regression = this.linearRegression(velTimestamps, velocities);
    return regression.slope;
  }

  /**
   * Coefficient of Variation (değişkenlik katsayısı)
   */
  static coefficientOfVariation(values: number[]): number {
    const mean = this.mean(values);
    if (mean === 0) return 0;
    return this.stdDev(values) / Math.abs(mean);
  }
}

// ============================================================================
// ANOMALY DETECTOR
// ============================================================================

class AnomalyDetector {
  private config: InsightEngineConfig;

  constructor(config: InsightEngineConfig) {
    this.config = config;
  }

  /**
   * Z-score tabanlı anomaly detection
   */
  detectWithZScore(value: number, historicalValues: number[]): AnomalyResult {
    const mean = StatUtils.mean(historicalValues);
    const stdDev = StatUtils.stdDev(historicalValues);
    const zScore = StatUtils.zScore(value, mean, stdDev);
    const absZScore = Math.abs(zScore);

    return {
      isAnomaly: absZScore > this.config.anomalyThreshold,
      score: Math.min(absZScore / (this.config.anomalyThreshold * 2), 1),
      direction: zScore > this.config.anomalyThreshold ? 'high' : zScore < -this.config.anomalyThreshold ? 'low' : 'normal',
      expectedValue: mean,
      actualValue: value,
      deviation: zScore,
      method: 'zscore',
    };
  }

  /**
   * IQR tabanlı anomaly detection (outlier'lara daha dayanıklı)
   */
  detectWithIQR(value: number, historicalValues: number[]): AnomalyResult {
    const { q1, q3, lowerBound, upperBound, iqr } = StatUtils.iqr(historicalValues);
    const median = StatUtils.median(historicalValues);
    
    const isAnomaly = value < lowerBound || value > upperBound;
    const deviation = iqr !== 0 ? (value - median) / iqr : 0;

    return {
      isAnomaly,
      score: Math.min(Math.abs(deviation) / 3, 1), // 3 IQR = max score
      direction: value > upperBound ? 'high' : value < lowerBound ? 'low' : 'normal',
      expectedValue: median,
      actualValue: value,
      deviation,
      method: 'iqr',
    };
  }

  /**
   * MAD tabanlı anomaly detection (en robust yöntem)
   */
  detectWithMAD(value: number, historicalValues: number[]): AnomalyResult {
    const median = StatUtils.median(historicalValues);
    const mad = StatUtils.mad(historicalValues);
    
    // Modified Z-score using MAD
    const modifiedZScore = mad !== 0 ? 0.6745 * (value - median) / mad : 0;
    const absScore = Math.abs(modifiedZScore);
    const threshold = 3.5; // Daha conservative threshold for MAD

    return {
      isAnomaly: absScore > threshold,
      score: Math.min(absScore / (threshold * 2), 1),
      direction: modifiedZScore > threshold ? 'high' : modifiedZScore < -threshold ? 'low' : 'normal',
      expectedValue: median,
      actualValue: value,
      deviation: modifiedZScore,
      method: 'mad',
    };
  }

  /**
   * Ensemble anomaly detection (tüm yöntemlerin birleşimi)
   */
  detect(value: number, historicalValues: number[]): AnomalyResult {
    if (historicalValues.length < 5) {
      // Yeterli veri yok, basit threshold kullan
      return {
        isAnomaly: false,
        score: 0,
        direction: 'normal',
        expectedValue: value,
        actualValue: value,
        deviation: 0,
        method: 'zscore',
      };
    }

    const zScoreResult = this.detectWithZScore(value, historicalValues);
    const iqrResult = this.detectWithIQR(value, historicalValues);
    const madResult = this.detectWithMAD(value, historicalValues);

    // Voting: en az 2 yöntem anomaly derse anomaly
    const anomalyVotes = [zScoreResult, iqrResult, madResult].filter(r => r.isAnomaly).length;
    const isAnomaly = anomalyVotes >= 2;

    // En yüksek confidence olan sonucu kullan
    const avgScore = (zScoreResult.score + iqrResult.score + madResult.score) / 3;
    const bestResult = [zScoreResult, iqrResult, madResult].reduce((best, curr) => 
      curr.score > best.score ? curr : best
    );

    return {
      ...bestResult,
      isAnomaly,
      score: avgScore,
    };
  }

  /**
   * Contextual anomaly detection (zaman bazlı)
   */
  detectContextual(
    value: number, 
    historicalValues: number[], 
    timestamps: number[],
    currentTimestamp: number
  ): AnomalyResult & { contextualInfo: string } {
    const baseResult = this.detect(value, historicalValues);
    
    // Saat bazlı context
    const currentHour = new Date(currentTimestamp).getHours();
    const isBusinessHours = currentHour >= 9 && currentHour <= 18;
    const isNightTime = currentHour >= 0 && currentHour <= 6;
    
    // Aynı saatteki historical değerleri filtrele
    const sameHourValues = historicalValues.filter((_, i) => {
      const hour = new Date(timestamps[i]).getHours();
      return Math.abs(hour - currentHour) <= 1; // ±1 saat tolerans
    });

    let contextualInfo = '';
    let adjustedScore = baseResult.score;

    if (sameHourValues.length >= 3) {
      const contextResult = this.detect(value, sameHourValues);
      // Contextual anomaly daha güçlü sinyal
      if (contextResult.isAnomaly && baseResult.isAnomaly) {
        adjustedScore = Math.min(baseResult.score * 1.3, 1);
        contextualInfo = 'Anomaly confirmed in same time-of-day context';
      } else if (!contextResult.isAnomaly && baseResult.isAnomaly) {
        adjustedScore = baseResult.score * 0.7;
        contextualInfo = 'Anomaly may be normal for this time of day';
      }
    }

    if (isNightTime && baseResult.direction === 'low') {
      adjustedScore *= 0.5; // Gece düşük aktivite normal
      contextualInfo = 'Low activity is typical during night hours';
    }

    return {
      ...baseResult,
      score: adjustedScore,
      contextualInfo,
    };
  }
}

// ============================================================================
// TREND ANALYZER
// ============================================================================

class TrendAnalyzer {
  private config: InsightEngineConfig;

  constructor(config: InsightEngineConfig) {
    this.config = config;
  }

  /**
   * Trend analizi yap
   */
  analyze(values: number[], timestamps: number[]): TrendResult {
    if (values.length < 3) {
      return {
        direction: 'stable',
        velocity: 0,
        acceleration: 0,
        confidence: 0,
        prediction: { nextValue: values[values.length - 1] || 0, nextHour: values[values.length - 1] || 0, confidence: 0 },
      };
    }

    const regression = StatUtils.linearRegression(timestamps, values);
    const velocity = StatUtils.velocity(values, timestamps);
    const acceleration = StatUtils.acceleration(values, timestamps);
    const cv = StatUtils.coefficientOfVariation(values);

    // Direction belirleme
    let direction: TrendResult['direction'];
    const velocityThreshold = StatUtils.stdDev(values) * 0.1; // %10 std dev

    if (cv > 0.5) {
      direction = 'volatile';
    } else if (Math.abs(velocity) < velocityThreshold) {
      direction = 'stable';
    } else if (velocity > 0) {
      direction = 'increasing';
    } else {
      direction = 'decreasing';
    }

    // Confidence: R² ve volatilite'ye göre
    const confidence = Math.max(0, Math.min(1, regression.r2 * (1 - cv)));

    // Prediction
    const lastTimestamp = timestamps[timestamps.length - 1];
    const nextTimestamp = lastTimestamp + 60000; // +1 dakika
    const nextHourTimestamp = lastTimestamp + 3600000; // +1 saat

    const predictNext = regression.slope * nextTimestamp + regression.intercept;
    const predictNextHour = regression.slope * nextHourTimestamp + regression.intercept;

    return {
      direction,
      velocity,
      acceleration,
      confidence,
      prediction: {
        nextValue: Math.max(0, predictNext),
        nextHour: Math.max(0, predictNextHour),
        confidence: confidence * 0.8, // Prediction confidence biraz daha düşük
      },
    };
  }

  /**
   * Trend değişimi tespit et
   */
  detectTrendChange(values: number[], timestamps: number[], windowSize: number = 5): {
    hasChange: boolean;
    changePoint?: number;
    previousTrend: TrendResult['direction'];
    newTrend: TrendResult['direction'];
  } {
    if (values.length < windowSize * 2) {
      return { hasChange: false, previousTrend: 'stable', newTrend: 'stable' };
    }

    const midPoint = Math.floor(values.length / 2);
    
    const firstHalf = values.slice(0, midPoint);
    const firstTimestamps = timestamps.slice(0, midPoint);
    const secondHalf = values.slice(midPoint);
    const secondTimestamps = timestamps.slice(midPoint);

    const firstTrend = this.analyze(firstHalf, firstTimestamps);
    const secondTrend = this.analyze(secondHalf, secondTimestamps);

    const hasChange = firstTrend.direction !== secondTrend.direction;

    return {
      hasChange,
      changePoint: hasChange ? timestamps[midPoint] : undefined,
      previousTrend: firstTrend.direction,
      newTrend: secondTrend.direction,
    };
  }
}

// ============================================================================
// CORRELATION ANALYZER
// ============================================================================

class CorrelationAnalyzer {
  private config: InsightEngineConfig;

  constructor(config: InsightEngineConfig) {
    this.config = config;
  }

  /**
   * İki metrik arasındaki korelasyonu analiz et
   */
  analyze(
    series1: MetricSeries, 
    series2: MetricSeries,
    maxLagMinutes: number = 30
  ): CorrelationResult {
    // Timestamp'leri hizala
    const { aligned1, aligned2 } = this.alignSeries(series1, series2);
    
    if (aligned1.length < 5) {
      return {
        metric1: series1.name,
        metric2: series2.name,
        coefficient: 0,
        strength: 'none',
        direction: 'none',
        lagMinutes: 0,
        causality: 'unlikely',
      };
    }

    // Lag analizi: farklı lag değerleri için korelasyon hesapla
    let bestCorrelation = 0;
    let bestLag = 0;

    for (let lag = 0; lag <= maxLagMinutes; lag += 5) {
      const laggedCorr = this.calculateLaggedCorrelation(aligned1, aligned2, lag);
      if (Math.abs(laggedCorr) > Math.abs(bestCorrelation)) {
        bestCorrelation = laggedCorr;
        bestLag = lag;
      }
    }

    const absCorr = Math.abs(bestCorrelation);
    let strength: CorrelationResult['strength'];
    if (absCorr >= 0.7) strength = 'strong';
    else if (absCorr >= 0.4) strength = 'moderate';
    else if (absCorr >= 0.2) strength = 'weak';
    else strength = 'none';

    const direction: CorrelationResult['direction'] = 
      absCorr < 0.2 ? 'none' : bestCorrelation > 0 ? 'positive' : 'negative';

    // Causality tahmini: güçlü korelasyon + pozitif lag = olası nedensellik
    let causality: CorrelationResult['causality'] = 'unlikely';
    if (strength === 'strong' && bestLag > 0) causality = 'likely';
    else if (strength === 'moderate' && bestLag > 0) causality = 'possible';

    return {
      metric1: series1.name,
      metric2: series2.name,
      coefficient: bestCorrelation,
      strength,
      direction,
      lagMinutes: bestLag,
      causality,
    };
  }

  private alignSeries(series1: MetricSeries, series2: MetricSeries): { aligned1: number[]; aligned2: number[] } {
    // Basit alignment: ortak timestamp'leri bul
    const map1 = new Map(series1.data.map(d => [Math.floor(d.timestamp / 60000), d.value]));
    const map2 = new Map(series2.data.map(d => [Math.floor(d.timestamp / 60000), d.value]));
    
    const aligned1: number[] = [];
    const aligned2: number[] = [];
    
    Array.from(map1.entries()).forEach(([minute, value1]) => {
      if (map2.has(minute)) {
        aligned1.push(value1);
        aligned2.push(map2.get(minute)!);
      }
    });
    
    return { aligned1, aligned2 };
  }

  private calculateLaggedCorrelation(values1: number[], values2: number[], lagMinutes: number): number {
    const lagPoints = Math.floor(lagMinutes / 5); // 5 dakikalık çözünürlük varsay
    
    if (lagPoints >= values1.length) return 0;
    
    const lagged1 = values1.slice(0, values1.length - lagPoints);
    const lagged2 = values2.slice(lagPoints);
    
    return StatUtils.correlation(lagged1, lagged2);
  }

  /**
   * Çoklu metrik korelasyon matrisi
   */
  analyzeMultiple(series: MetricSeries[]): CorrelationResult[] {
    const results: CorrelationResult[] = [];
    
    for (let i = 0; i < series.length; i++) {
      for (let j = i + 1; j < series.length; j++) {
        const result = this.analyze(series[i], series[j]);
        if (result.strength !== 'none') {
          results.push(result);
        }
      }
    }
    
    return results.sort((a, b) => Math.abs(b.coefficient) - Math.abs(a.coefficient));
  }
}

// ============================================================================
// PATTERN DETECTOR
// ============================================================================

class PatternDetector {
  private config: InsightEngineConfig;

  constructor(config: InsightEngineConfig) {
    this.config = config;
  }

  /**
   * Pattern'leri tespit et
   */
  detect(values: number[], timestamps: number[]): PatternResult[] {
    const patterns: PatternResult[] = [];

    // Spike detection
    const spikes = this.detectSpikes(values, timestamps);
    patterns.push(...spikes);

    // Dip detection
    const dips = this.detectDips(values, timestamps);
    patterns.push(...dips);

    // Step change detection
    const stepChanges = this.detectStepChanges(values, timestamps);
    patterns.push(...stepChanges);

    // Oscillation detection
    const oscillations = this.detectOscillations(values, timestamps);
    patterns.push(...oscillations);

    return patterns;
  }

  private detectSpikes(values: number[], timestamps: number[]): PatternResult[] {
    const spikes: PatternResult[] = [];
    const mean = StatUtils.mean(values);
    const stdDev = StatUtils.stdDev(values);
    const threshold = mean + 2.5 * stdDev;

    let inSpike = false;
    let spikeStart = 0;
    let maxValue = 0;

    for (let i = 0; i < values.length; i++) {
      if (values[i] > threshold && !inSpike) {
        inSpike = true;
        spikeStart = timestamps[i];
        maxValue = values[i];
      } else if (values[i] > threshold && inSpike) {
        maxValue = Math.max(maxValue, values[i]);
      } else if (values[i] <= threshold && inSpike) {
        inSpike = false;
        spikes.push({
          type: 'spike',
          startTime: spikeStart,
          endTime: timestamps[i],
          magnitude: (maxValue - mean) / stdDev,
          isRecurring: false,
        });
      }
    }

    // Recurring pattern kontrolü
    if (spikes.length >= 3) {
      const intervals = [];
      for (let i = 1; i < spikes.length; i++) {
        intervals.push(spikes[i].startTime - spikes[i - 1].startTime);
      }
      const avgInterval = StatUtils.mean(intervals);
      const intervalStdDev = StatUtils.stdDev(intervals);
      
      if (intervalStdDev / avgInterval < 0.3) { // %30'dan az varyasyon
        const hourly = avgInterval >= 3000000 && avgInterval <= 4200000;
        const daily = avgInterval >= 79200000 && avgInterval <= 90000000;
        
        spikes.forEach(spike => {
          spike.isRecurring = true;
          spike.recurringPattern = hourly ? 'hourly' : daily ? 'daily' : undefined;
        });
      }
    }

    return spikes;
  }

  private detectDips(values: number[], timestamps: number[]): PatternResult[] {
    const dips: PatternResult[] = [];
    const mean = StatUtils.mean(values);
    const stdDev = StatUtils.stdDev(values);
    const threshold = mean - 2 * stdDev;

    let inDip = false;
    let dipStart = 0;
    let minValue = Infinity;

    for (let i = 0; i < values.length; i++) {
      if (values[i] < threshold && !inDip) {
        inDip = true;
        dipStart = timestamps[i];
        minValue = values[i];
      } else if (values[i] < threshold && inDip) {
        minValue = Math.min(minValue, values[i]);
      } else if (values[i] >= threshold && inDip) {
        inDip = false;
        dips.push({
          type: 'dip',
          startTime: dipStart,
          endTime: timestamps[i],
          magnitude: (mean - minValue) / stdDev,
          isRecurring: false,
        });
      }
    }

    return dips;
  }

  private detectStepChanges(values: number[], timestamps: number[]): PatternResult[] {
    const changes: PatternResult[] = [];
    const windowSize = Math.max(5, Math.floor(values.length / 10));

    for (let i = windowSize; i < values.length - windowSize; i++) {
      const before = values.slice(i - windowSize, i);
      const after = values.slice(i, i + windowSize);
      
      const beforeMean = StatUtils.mean(before);
      const afterMean = StatUtils.mean(after);
      const overallStdDev = StatUtils.stdDev(values);
      
      const change = Math.abs(afterMean - beforeMean);
      
      if (change > 2 * overallStdDev) {
        changes.push({
          type: 'step_change',
          startTime: timestamps[i],
          magnitude: change / overallStdDev,
          isRecurring: false,
        });
        i += windowSize; // Skip ahead to avoid duplicate detection
      }
    }

    return changes;
  }

  private detectOscillations(values: number[], timestamps: number[]): PatternResult[] {
    const oscillations: PatternResult[] = [];
    
    // Zero-crossing count
    const mean = StatUtils.mean(values);
    const centered = values.map(v => v - mean);
    
    let crossings = 0;
    for (let i = 1; i < centered.length; i++) {
      if (centered[i] * centered[i - 1] < 0) {
        crossings++;
      }
    }
    
    const expectedCrossings = values.length / 4; // Random için beklenen
    
    if (crossings > expectedCrossings * 2) {
      const period = (timestamps[timestamps.length - 1] - timestamps[0]) / crossings * 2;
      oscillations.push({
        type: 'oscillation',
        startTime: timestamps[0],
        endTime: timestamps[timestamps.length - 1],
        magnitude: StatUtils.stdDev(values) / mean,
        frequency: 1 / period,
        isRecurring: true,
      });
    }

    return oscillations;
  }
}

// ============================================================================
// ROOT CAUSE ANALYZER
// ============================================================================

class RootCauseAnalyzer {
  /**
   * Potansiyel root cause'ları analiz et
   */
  analyze(
    targetMetric: string,
    targetAnomaly: AnomalyResult,
    correlations: CorrelationResult[],
    allMetrics: Map<string, { value: number; anomaly?: AnomalyResult; trend?: TrendResult }>
  ): RootCauseCandidate[] {
    const candidates: RootCauseCandidate[] = [];

    // Correlation-based candidates
    const relatedCorrelations = correlations.filter(
      c => (c.metric1 === targetMetric || c.metric2 === targetMetric) && 
           c.strength !== 'none' && 
           c.causality !== 'unlikely'
    );

    for (const corr of relatedCorrelations) {
      const otherMetric = corr.metric1 === targetMetric ? corr.metric2 : corr.metric1;
      const otherData = allMetrics.get(otherMetric);
      
      if (!otherData) continue;

      let probability = 0;
      const evidence: string[] = [];

      // Korelasyon gücüne göre base probability
      if (corr.strength === 'strong') probability += 0.4;
      else if (corr.strength === 'moderate') probability += 0.2;

      // Lag varsa ve doğru yönde ise
      if (corr.lagMinutes > 0) {
        probability += 0.2;
        evidence.push(`${otherMetric} changes precede ${targetMetric} by ~${corr.lagMinutes} minutes`);
      }

      // Diğer metrikte de anomaly varsa
      if (otherData.anomaly?.isAnomaly) {
        probability += 0.3;
        evidence.push(`${otherMetric} also shows anomalous behavior`);
      }

      // Aynı yönde trend varsa
      if (otherData.trend && targetAnomaly.direction !== 'normal') {
        const trendMatchesAnomaly = 
          (targetAnomaly.direction === 'high' && otherData.trend.direction === 'increasing') ||
          (targetAnomaly.direction === 'low' && otherData.trend.direction === 'decreasing');
        
        if (trendMatchesAnomaly) {
          probability += 0.1;
          evidence.push(`${otherMetric} trend aligns with anomaly direction`);
        }
      }

      if (probability > 0.3) {
        candidates.push({
          metric: otherMetric,
          probability: Math.min(probability, 0.95),
          evidence,
          suggestedAction: this.generateAction(otherMetric, otherData),
          relatedMetrics: [targetMetric],
        });
      }
    }

    // Domain-specific heuristics
    candidates.push(...this.applyDomainHeuristics(targetMetric, targetAnomaly, allMetrics));

    return candidates.sort((a, b) => b.probability - a.probability);
  }

  private generateAction(metric: string, data: { value: number; anomaly?: AnomalyResult; trend?: TrendResult }): string {
    const metricLower = metric.toLowerCase();
    
    if (metricLower.includes('error') || metricLower.includes('fail')) {
      return 'Review error logs and recent deployments';
    }
    if (metricLower.includes('memory') || metricLower.includes('oom')) {
      return 'Check memory limits and consider scaling or optimization';
    }
    if (metricLower.includes('cpu')) {
      return 'Review CPU-intensive operations and consider horizontal scaling';
    }
    if (metricLower.includes('latency') || metricLower.includes('response')) {
      return 'Check network conditions and downstream dependencies';
    }
    if (metricLower.includes('connection') || metricLower.includes('network')) {
      return 'Verify network policies and connection pool settings';
    }
    
    return `Investigate ${metric} for potential issues`;
  }

  private applyDomainHeuristics(
    targetMetric: string,
    targetAnomaly: AnomalyResult,
    allMetrics: Map<string, { value: number; anomaly?: AnomalyResult; trend?: TrendResult }>
  ): RootCauseCandidate[] {
    const candidates: RootCauseCandidate[] = [];
    const metricLower = targetMetric.toLowerCase();

    // Error rate high → check latency and resource usage
    if (metricLower.includes('error') && targetAnomaly.direction === 'high') {
      const latencyMetric = Array.from(allMetrics.entries()).find(([k]) => k.toLowerCase().includes('latency'));
      const memoryMetric = Array.from(allMetrics.entries()).find(([k]) => k.toLowerCase().includes('memory'));
      
      if (latencyMetric?.[1].anomaly?.isAnomaly) {
        candidates.push({
          metric: latencyMetric[0],
          probability: 0.7,
          evidence: ['High latency often causes timeout errors', 'Latency anomaly detected'],
          suggestedAction: 'Check slow queries and network bottlenecks',
          relatedMetrics: [targetMetric],
        });
      }
      
      if (memoryMetric?.[1].anomaly?.isAnomaly) {
        candidates.push({
          metric: memoryMetric[0],
          probability: 0.6,
          evidence: ['Memory pressure can cause errors', 'Memory anomaly detected'],
          suggestedAction: 'Review memory allocation and check for leaks',
          relatedMetrics: [targetMetric],
        });
      }
    }

    // Latency high → check CPU and connection count
    if (metricLower.includes('latency') && targetAnomaly.direction === 'high') {
      const cpuMetric = Array.from(allMetrics.entries()).find(([k]) => k.toLowerCase().includes('cpu'));
      const connMetric = Array.from(allMetrics.entries()).find(([k]) => k.toLowerCase().includes('connection'));
      
      if (cpuMetric?.[1].anomaly?.isAnomaly || (cpuMetric?.[1].value ?? 0) > 80) {
        candidates.push({
          metric: cpuMetric![0],
          probability: 0.65,
          evidence: ['High CPU causes processing delays', 'CPU usage elevated'],
          suggestedAction: 'Scale horizontally or optimize CPU-intensive operations',
          relatedMetrics: [targetMetric],
        });
      }
      
      if (connMetric?.[1].anomaly?.direction === 'high') {
        candidates.push({
          metric: connMetric[0],
          probability: 0.55,
          evidence: ['Connection saturation causes queuing', 'Connection count anomaly'],
          suggestedAction: 'Review connection pool limits and client connection patterns',
          relatedMetrics: [targetMetric],
        });
      }
    }

    return candidates;
  }
}

// ============================================================================
// INSIGHT GENERATOR
// ============================================================================

class InsightGenerator {
  private config: InsightEngineConfig;

  constructor(config: InsightEngineConfig) {
    this.config = config;
  }

  /**
   * Anomaly'den insight oluştur
   */
  fromAnomaly(
    metricName: string,
    anomaly: AnomalyResult,
    context?: { trend?: TrendResult; pattern?: PatternResult }
  ): SmartInsight | null {
    if (!anomaly.isAnomaly) return null;

    const severity = this.calculateSeverity(anomaly.score, metricName);
    const id = `anomaly-${metricName}-${Date.now()}`;

    let title = '';
    let description = '';
    const suggestedActions: string[] = [];

    if (anomaly.direction === 'high') {
      title = `Unusual spike in ${this.formatMetricName(metricName)}`;
      description = `${this.formatMetricName(metricName)} is ${anomaly.deviation.toFixed(1)} standard deviations above normal. `;
      description += `Current: ${this.formatValue(anomaly.actualValue, metricName)}, Expected: ~${this.formatValue(anomaly.expectedValue, metricName)}.`;
      
      suggestedActions.push(`Investigate recent changes that may have caused the ${metricName} increase`);
      if (metricName.toLowerCase().includes('error')) {
        suggestedActions.push('Check application logs for error details');
      }
      if (metricName.toLowerCase().includes('latency')) {
        suggestedActions.push('Review slow requests and database queries');
      }
    } else {
      title = `Unexpected drop in ${this.formatMetricName(metricName)}`;
      description = `${this.formatMetricName(metricName)} is ${Math.abs(anomaly.deviation).toFixed(1)} standard deviations below normal. `;
      description += `Current: ${this.formatValue(anomaly.actualValue, metricName)}, Expected: ~${this.formatValue(anomaly.expectedValue, metricName)}.`;
      
      suggestedActions.push(`Verify that the ${metricName} drop is expected`);
      if (metricName.toLowerCase().includes('traffic') || metricName.toLowerCase().includes('request')) {
        suggestedActions.push('Check for upstream issues or routing problems');
      }
    }

    // Add trend context
    if (context?.trend) {
      if (context.trend.direction === 'increasing' && anomaly.direction === 'high') {
        description += ` The metric has been trending upward, suggesting a developing issue.`;
      } else if (context.trend.direction === 'volatile') {
        description += ` High volatility detected, which may indicate system instability.`;
      }
    }

    return {
      id,
      type: 'anomaly',
      severity,
      confidence: anomaly.score,
      title,
      description,
      technicalDetail: `Detection method: ${anomaly.method}, Z-score: ${anomaly.deviation.toFixed(2)}`,
      metric: metricName,
      value: this.formatValue(anomaly.actualValue, metricName),
      anomaly,
      trend: context?.trend,
      pattern: context?.pattern,
      suggestedActions,
      tags: this.generateTags(metricName, 'anomaly'),
    };
  }

  /**
   * Trend'den insight oluştur
   */
  fromTrend(metricName: string, trend: TrendResult): SmartInsight | null {
    if (trend.direction === 'stable' || trend.confidence < 0.5) return null;

    const id = `trend-${metricName}-${Date.now()}`;
    let severity: SmartInsight['severity'] = 'info';
    let title = '';
    let description = '';
    const suggestedActions: string[] = [];

    if (trend.direction === 'increasing') {
      title = `${this.formatMetricName(metricName)} is trending upward`;
      
      // Kritik metrikler için severity artır
      if (metricName.toLowerCase().includes('error') || metricName.toLowerCase().includes('fail')) {
        severity = trend.velocity > 0.5 ? 'high' : 'medium';
        description = `Error rate is steadily increasing. If this trend continues, it may impact system reliability.`;
        suggestedActions.push('Monitor closely and prepare for potential incident');
        suggestedActions.push('Review recent deployments or configuration changes');
      } else if (metricName.toLowerCase().includes('latency')) {
        severity = trend.velocity > 0.3 ? 'medium' : 'low';
        description = `Response times are gradually increasing, which may affect user experience.`;
        suggestedActions.push('Investigate potential performance degradation sources');
      } else {
        description = `${this.formatMetricName(metricName)} has been consistently increasing.`;
      }
    } else if (trend.direction === 'decreasing') {
      title = `${this.formatMetricName(metricName)} is trending downward`;
      
      if (metricName.toLowerCase().includes('throughput') || metricName.toLowerCase().includes('traffic')) {
        severity = 'medium';
        description = `Traffic is decreasing, which may indicate an issue with incoming requests.`;
        suggestedActions.push('Verify that upstream services are healthy');
      } else if (metricName.toLowerCase().includes('error')) {
        severity = 'info';
        description = `Error rate is improving! Continue monitoring to ensure the trend holds.`;
      } else {
        description = `${this.formatMetricName(metricName)} has been consistently decreasing.`;
      }
    } else if (trend.direction === 'volatile') {
      title = `${this.formatMetricName(metricName)} showing high volatility`;
      severity = 'medium';
      description = `The metric is fluctuating significantly, which may indicate system instability or external factors.`;
      suggestedActions.push('Investigate the source of variability');
      suggestedActions.push('Consider implementing rate limiting or circuit breakers');
    }

    // Prediction ekle
    if (trend.prediction.confidence > 0.5) {
      description += ` Predicted value in 1 hour: ~${this.formatValue(trend.prediction.nextHour, metricName)}.`;
    }

    return {
      id,
      type: 'trend',
      severity,
      confidence: trend.confidence,
      title,
      description,
      technicalDetail: `Velocity: ${trend.velocity.toFixed(4)}/min, Acceleration: ${trend.acceleration.toFixed(6)}/min²`,
      metric: metricName,
      trend,
      suggestedActions,
      tags: this.generateTags(metricName, 'trend'),
    };
  }

  /**
   * Correlation'dan insight oluştur
   */
  fromCorrelation(correlation: CorrelationResult): SmartInsight | null {
    if (correlation.strength === 'none' || correlation.strength === 'weak') return null;

    const id = `correlation-${correlation.metric1}-${correlation.metric2}-${Date.now()}`;
    const severity: SmartInsight['severity'] = correlation.causality === 'likely' ? 'medium' : 'low';

    let title = `${this.formatMetricName(correlation.metric1)} and ${this.formatMetricName(correlation.metric2)} are correlated`;
    let description = `These metrics show a ${correlation.strength} ${correlation.direction} correlation (r=${correlation.coefficient.toFixed(2)}).`;
    
    if (correlation.lagMinutes > 0) {
      description += ` Changes in ${correlation.metric1} appear to precede ${correlation.metric2} by approximately ${correlation.lagMinutes} minutes.`;
    }

    const suggestedActions: string[] = [];
    if (correlation.causality === 'likely') {
      suggestedActions.push(`When investigating ${correlation.metric2} issues, check ${correlation.metric1} first`);
    }
    suggestedActions.push(`Consider setting up correlated alerts for these metrics`);

    return {
      id,
      type: 'correlation',
      severity,
      confidence: Math.abs(correlation.coefficient),
      title,
      description,
      correlation,
      suggestedActions,
      tags: [...this.generateTags(correlation.metric1, 'correlation'), ...this.generateTags(correlation.metric2, 'correlation')],
    };
  }

  /**
   * Pattern'den insight oluştur
   */
  fromPattern(metricName: string, pattern: PatternResult): SmartInsight | null {
    const id = `pattern-${metricName}-${pattern.type}-${Date.now()}`;
    let severity: SmartInsight['severity'] = 'info';
    let title = '';
    let description = '';
    const suggestedActions: string[] = [];

    switch (pattern.type) {
      case 'spike':
        title = `Spike detected in ${this.formatMetricName(metricName)}`;
        severity = pattern.magnitude > 3 ? 'high' : 'medium';
        description = `A sudden spike of ${pattern.magnitude.toFixed(1)}σ was detected.`;
        if (pattern.isRecurring) {
          description += ` This appears to be a recurring ${pattern.recurringPattern || ''} pattern.`;
          severity = 'low'; // Recurring patterns are less concerning
        }
        suggestedActions.push('Investigate the cause of the spike');
        break;

      case 'dip':
        title = `Dip detected in ${this.formatMetricName(metricName)}`;
        severity = pattern.magnitude > 3 ? 'high' : 'medium';
        description = `A sudden drop of ${pattern.magnitude.toFixed(1)}σ was detected.`;
        suggestedActions.push('Check for service disruptions or data collection issues');
        break;

      case 'step_change':
        title = `Step change in ${this.formatMetricName(metricName)}`;
        severity = 'medium';
        description = `The baseline for this metric appears to have shifted. This often indicates a configuration change or deployment.`;
        suggestedActions.push('Review recent changes and update baseline expectations if intentional');
        break;

      case 'oscillation':
        title = `Oscillation pattern in ${this.formatMetricName(metricName)}`;
        severity = 'low';
        description = `The metric is oscillating with a frequency of ${((pattern.frequency || 0) * 60).toFixed(2)} cycles/hour.`;
        suggestedActions.push('Investigate potential feedback loops or periodic processes');
        break;

      default:
        return null;
    }

    return {
      id,
      type: 'pattern',
      severity,
      confidence: Math.min(pattern.magnitude / 5, 1),
      title,
      description,
      metric: metricName,
      pattern,
      suggestedActions,
      tags: this.generateTags(metricName, 'pattern'),
    };
  }

  /**
   * Root cause'dan insight oluştur
   */
  fromRootCause(targetMetric: string, candidates: RootCauseCandidate[]): SmartInsight | null {
    if (candidates.length === 0) return null;

    const topCandidate = candidates[0];
    const id = `rootcause-${targetMetric}-${Date.now()}`;

    const title = `Potential root cause identified for ${this.formatMetricName(targetMetric)} issue`;
    let description = `${this.formatMetricName(topCandidate.metric)} may be contributing to the ${targetMetric} anomaly `;
    description += `(${(topCandidate.probability * 100).toFixed(0)}% confidence).`;
    
    if (topCandidate.evidence.length > 0) {
      description += ` Evidence: ${topCandidate.evidence[0]}.`;
    }

    const suggestedActions = [topCandidate.suggestedAction];
    if (candidates.length > 1) {
      suggestedActions.push(`Also investigate: ${candidates.slice(1, 3).map(c => c.metric).join(', ')}`);
    }

    return {
      id,
      type: 'root_cause',
      severity: topCandidate.probability > 0.7 ? 'high' : 'medium',
      confidence: topCandidate.probability,
      title,
      description,
      technicalDetail: `Evidence: ${topCandidate.evidence.join('; ')}`,
      metric: targetMetric,
      rootCause: candidates,
      suggestedActions,
      relatedInsights: candidates.map(c => c.metric),
      tags: this.generateTags(targetMetric, 'root_cause'),
    };
  }

  /**
   * Prediction insight oluştur
   */
  fromPrediction(metricName: string, trend: TrendResult, currentValue: number): SmartInsight | null {
    if (trend.prediction.confidence < 0.6) return null;

    const predictedChange = (trend.prediction.nextHour - currentValue) / (currentValue || 1) * 100;
    if (Math.abs(predictedChange) < 20) return null; // %20'den az değişim önemsiz

    const id = `prediction-${metricName}-${Date.now()}`;
    const isIncrease = predictedChange > 0;
    
    let severity: SmartInsight['severity'] = 'info';
    if (Math.abs(predictedChange) > 50) severity = 'medium';
    if (Math.abs(predictedChange) > 100) severity = 'high';

    // Error veya latency artışı daha kritik
    if (metricName.toLowerCase().includes('error') && isIncrease) {
      severity = predictedChange > 30 ? 'high' : 'medium';
    }

    const title = `${this.formatMetricName(metricName)} predicted to ${isIncrease ? 'increase' : 'decrease'} by ${Math.abs(predictedChange).toFixed(0)}%`;
    const description = `Based on current trends, ${metricName} is expected to reach ~${this.formatValue(trend.prediction.nextHour, metricName)} within the next hour (${(trend.prediction.confidence * 100).toFixed(0)}% confidence).`;

    const suggestedActions: string[] = [];
    if (isIncrease && severity !== 'info') {
      suggestedActions.push('Consider proactive scaling or alerting');
      suggestedActions.push('Review capacity planning');
    }

    return {
      id,
      type: 'prediction',
      severity,
      confidence: trend.prediction.confidence,
      title,
      description,
      metric: metricName,
      value: this.formatValue(trend.prediction.nextHour, metricName),
      trend,
      suggestedActions,
      expiresAt: Date.now() + 3600000, // 1 saat sonra expire
      tags: this.generateTags(metricName, 'prediction'),
    };
  }

  /**
   * Healthy system recommendation
   */
  createHealthySystemInsight(): SmartInsight {
    return {
      id: `healthy-${Date.now()}`,
      type: 'recommendation',
      severity: 'info',
      confidence: 1,
      title: 'System Operating Normally',
      description: 'All metrics are within expected ranges. No anomalies or concerning trends detected.',
      suggestedActions: [
        'Continue monitoring for any changes',
        'Consider setting up automated alerts for key metrics',
        'Review and optimize resource allocation for cost efficiency',
      ],
      tags: ['healthy', 'recommendation'],
    };
  }

  // Helper methods
  private calculateSeverity(score: number, metricName: string): SmartInsight['severity'] {
    // Kritik metrikler için severity boost
    const isCriticalMetric = 
      metricName.toLowerCase().includes('error') ||
      metricName.toLowerCase().includes('fail') ||
      metricName.toLowerCase().includes('oom') ||
      metricName.toLowerCase().includes('critical');

    const boost = isCriticalMetric ? 0.2 : 0;
    const adjustedScore = Math.min(score + boost, 1);

    if (adjustedScore >= 0.8) return 'critical';
    if (adjustedScore >= 0.6) return 'high';
    if (adjustedScore >= 0.4) return 'medium';
    if (adjustedScore >= 0.2) return 'low';
    return 'info';
  }

  private formatMetricName(name: string): string {
    return name
      .replace(/_/g, ' ')
      .replace(/([A-Z])/g, ' $1')
      .trim()
      .split(' ')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
      .join(' ');
  }

  private formatValue(value: number, metricName: string): string {
    const nameLower = metricName.toLowerCase();
    
    if (nameLower.includes('percent') || nameLower.includes('rate') || nameLower.includes('ratio')) {
      return `${value.toFixed(1)}%`;
    }
    if (nameLower.includes('latency') || nameLower.includes('time') || nameLower.includes('duration')) {
      return `${value.toFixed(0)}ms`;
    }
    if (nameLower.includes('byte')) {
      if (value >= 1e9) return `${(value / 1e9).toFixed(1)}GB`;
      if (value >= 1e6) return `${(value / 1e6).toFixed(1)}MB`;
      if (value >= 1e3) return `${(value / 1e3).toFixed(1)}KB`;
      return `${value.toFixed(0)}B`;
    }
    if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
    if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
    return value.toFixed(value < 10 ? 2 : 0);
  }

  private generateTags(metricName: string, insightType: string): string[] {
    const tags: string[] = [insightType];
    const nameLower = metricName.toLowerCase();
    
    if (nameLower.includes('error') || nameLower.includes('fail')) tags.push('error', 'reliability');
    if (nameLower.includes('latency') || nameLower.includes('response')) tags.push('performance', 'latency');
    if (nameLower.includes('cpu') || nameLower.includes('memory')) tags.push('resource', 'capacity');
    if (nameLower.includes('network') || nameLower.includes('connection')) tags.push('network');
    if (nameLower.includes('security') || nameLower.includes('denied')) tags.push('security');
    if (nameLower.includes('oom')) tags.push('memory', 'critical');
    
    return Array.from(new Set(tags));
  }
}

// ============================================================================
// MAIN ENGINE
// ============================================================================

export class InsightEngine {
  private config: InsightEngineConfig;
  private anomalyDetector: AnomalyDetector;
  private trendAnalyzer: TrendAnalyzer;
  private correlationAnalyzer: CorrelationAnalyzer;
  private patternDetector: PatternDetector;
  private rootCauseAnalyzer: RootCauseAnalyzer;
  private insightGenerator: InsightGenerator;

  constructor(config?: Partial<InsightEngineConfig>) {
    this.config = {
      anomalyThreshold: 2.5,
      trendWindowSize: 10,
      correlationMinStrength: 0.5,
      patternMinDuration: 300000, // 5 dakika
      predictionHorizon: 60,
      enabledAnalyses: {
        anomaly: true,
        trend: true,
        correlation: true,
        pattern: true,
        prediction: true,
        rootCause: true,
      },
      ...config,
    };

    this.anomalyDetector = new AnomalyDetector(this.config);
    this.trendAnalyzer = new TrendAnalyzer(this.config);
    this.correlationAnalyzer = new CorrelationAnalyzer(this.config);
    this.patternDetector = new PatternDetector(this.config);
    this.rootCauseAnalyzer = new RootCauseAnalyzer();
    this.insightGenerator = new InsightGenerator(this.config);
  }

  /**
   * Ana analiz metodu - tüm metrikleri analiz et ve insight'lar üret
   */
  analyze(metrics: Map<string, MetricSeries>): SmartInsight[] {
    const insights: SmartInsight[] = [];
    const metricAnalysis = new Map<string, { 
      value: number; 
      anomaly?: AnomalyResult; 
      trend?: TrendResult;
      patterns?: PatternResult[];
    }>();

    // 1. Her metrik için bireysel analiz
    for (const [name, series] of Array.from(metrics.entries())) {
      if (series.data.length < 3) continue;

      const values = series.data.map(d => d.value);
      const timestamps = series.data.map(d => d.timestamp);
      const currentValue = values[values.length - 1];
      const historicalValues = values.slice(0, -1);

      const analysis: { 
        value: number; 
        anomaly?: AnomalyResult; 
        trend?: TrendResult;
        patterns?: PatternResult[];
      } = { value: currentValue };

      // Anomaly detection
      if (this.config.enabledAnalyses.anomaly && historicalValues.length >= 5) {
        const anomaly = this.anomalyDetector.detect(currentValue, historicalValues);
        analysis.anomaly = anomaly;
      }

      // Trend analysis
      if (this.config.enabledAnalyses.trend) {
        const trend = this.trendAnalyzer.analyze(values, timestamps);
        analysis.trend = trend;
      }

      // Pattern detection
      if (this.config.enabledAnalyses.pattern && values.length >= 10) {
        const patterns = this.patternDetector.detect(values, timestamps);
        analysis.patterns = patterns;
      }

      metricAnalysis.set(name, analysis);
    }

    // 2. Correlation analysis
    let correlations: CorrelationResult[] = [];
    if (this.config.enabledAnalyses.correlation) {
      const seriesArray = Array.from(metrics.values());
      correlations = this.correlationAnalyzer.analyzeMultiple(seriesArray);
    }

    // 3. Insight generation
    for (const [name, analysis] of Array.from(metricAnalysis.entries())) {
      // Anomaly insights
      if (analysis.anomaly?.isAnomaly) {
        const insight = this.insightGenerator.fromAnomaly(name, analysis.anomaly, {
          trend: analysis.trend,
          pattern: analysis.patterns?.[0],
        });
        if (insight) insights.push(insight);

        // Root cause analysis for anomalies
        if (this.config.enabledAnalyses.rootCause) {
          const candidates = this.rootCauseAnalyzer.analyze(
            name,
            analysis.anomaly,
            correlations,
            metricAnalysis
          );
          const rootCauseInsight = this.insightGenerator.fromRootCause(name, candidates);
          if (rootCauseInsight) insights.push(rootCauseInsight);
        }
      }

      // Trend insights
      if (analysis.trend && analysis.trend.direction !== 'stable') {
        const insight = this.insightGenerator.fromTrend(name, analysis.trend);
        if (insight) insights.push(insight);

        // Prediction insights
        if (this.config.enabledAnalyses.prediction) {
          const predictionInsight = this.insightGenerator.fromPrediction(
            name,
            analysis.trend,
            analysis.value
          );
          if (predictionInsight) insights.push(predictionInsight);
        }
      }

      // Pattern insights
      if (analysis.patterns) {
        for (const pattern of analysis.patterns.slice(0, 2)) { // Max 2 pattern per metric
          const insight = this.insightGenerator.fromPattern(name, pattern);
          if (insight) insights.push(insight);
        }
      }
    }

    // 4. Correlation insights
    if (this.config.enabledAnalyses.correlation) {
      for (const correlation of correlations.slice(0, 3)) { // Top 3 correlations
        const insight = this.insightGenerator.fromCorrelation(correlation);
        if (insight) insights.push(insight);
      }
    }

    // 5. Healthy system check
    const hasIssues = insights.some(i => 
      i.severity === 'critical' || i.severity === 'high' || i.severity === 'medium'
    );
    if (!hasIssues) {
      insights.push(this.insightGenerator.createHealthySystemInsight());
    }

    // Sort by severity and confidence
    const severityOrder = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    return insights.sort((a, b) => {
      const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
      if (severityDiff !== 0) return severityDiff;
      return b.confidence - a.confidence;
    });
  }

  /**
   * Basit veri yapısından analiz (mevcut AIInsightCards uyumluluğu için)
   */
  analyzeSimple(data: {
    totalEvents?: number;
    eventCounts?: Record<string, number>;
    totalCommunications?: number;
    totalErrors?: number;
    totalRetransmits?: number;
    avgLatencyMs?: number;
    activeWorkloads?: number;
    totalWorkloads?: number;
    failedPods?: number;
    securityEvents?: number;
    deniedEvents?: number;
    criticalCapabilities?: number;
    totalChanges?: number;
    criticalChanges?: number;
    highRiskChanges?: number;
    oomEvents?: number;
    // Historical data for comparison
    previousPeriod?: {
      totalEvents?: number;
      totalCommunications?: number;
      totalErrors?: number;
      securityEvents?: number;
    };
  }): SmartInsight[] {
    const insights: SmartInsight[] = [];
    const now = Date.now();

    // Error rate analizi
    if (data.totalCommunications && data.totalCommunications > 0) {
      const errorRate = ((data.totalErrors || 0) + (data.totalRetransmits || 0)) / data.totalCommunications * 100;
      
      // Simüle edilmiş historical data ile anomaly detection
      const historicalErrorRates = [2, 2.5, 1.8, 3, 2.2, 1.9, 2.8, 2.1]; // Tipik değerler
      const anomaly = this.anomalyDetector.detect(errorRate, historicalErrorRates);
      
      if (anomaly.isAnomaly) {
        const insight = this.insightGenerator.fromAnomaly('error_rate', anomaly);
        if (insight) {
          insight.value = `${errorRate.toFixed(1)}%`;
          insights.push(insight);
        }
      } else if (errorRate < 1) {
        insights.push({
          id: `success-error-rate-${now}`,
          type: 'recommendation',
          severity: 'info',
          confidence: 0.9,
          title: 'Excellent Network Reliability',
          description: `Error rate is only ${errorRate.toFixed(2)}%. Your services are communicating reliably with minimal failures.`,
          metric: 'error_rate',
          value: `${errorRate.toFixed(2)}%`,
          suggestedActions: ['Continue monitoring to maintain this level'],
          tags: ['network', 'reliability', 'success'],
        });
      }
    }

    // Latency analizi
    if (data.avgLatencyMs && data.avgLatencyMs > 0) {
      const historicalLatencies = [120, 150, 180, 200, 160, 140, 170, 190];
      const anomaly = this.anomalyDetector.detect(data.avgLatencyMs, historicalLatencies);
      
      if (data.avgLatencyMs > 500 || anomaly.isAnomaly) {
        insights.push({
          id: `latency-issue-${now}`,
          type: 'anomaly',
          severity: data.avgLatencyMs > 1000 ? 'critical' : data.avgLatencyMs > 500 ? 'high' : 'medium',
          confidence: anomaly.score,
          title: 'Elevated Network Latency',
          description: `Average latency is ${data.avgLatencyMs.toFixed(0)}ms, which is ${anomaly.deviation.toFixed(1)} standard deviations from normal. This may impact user experience and service reliability.`,
          metric: 'latency',
          value: `${data.avgLatencyMs.toFixed(0)}ms`,
          anomaly,
          suggestedActions: [
            'Check network congestion and bandwidth utilization',
            'Review slow database queries',
            'Investigate cross-region communication patterns',
          ],
          tags: ['performance', 'latency', 'network'],
        });
      } else if (data.avgLatencyMs < 100) {
        insights.push({
          id: `success-latency-${now}`,
          type: 'recommendation',
          severity: 'info',
          confidence: 0.9,
          title: 'Excellent Response Times',
          description: `Average latency is only ${data.avgLatencyMs.toFixed(0)}ms. Your services are responding quickly and efficiently.`,
          metric: 'latency',
          value: `${data.avgLatencyMs.toFixed(0)}ms`,
          suggestedActions: ['Monitor for any degradation'],
          tags: ['performance', 'latency', 'success'],
        });
      }
    }

    // OOM olayları
    if (data.oomEvents && data.oomEvents > 0) {
      const severity: SmartInsight['severity'] = data.oomEvents > 10 ? 'critical' : data.oomEvents > 5 ? 'high' : 'medium';
      insights.push({
        id: `oom-events-${now}`,
        type: 'anomaly',
        severity,
        confidence: Math.min(data.oomEvents / 10, 1),
        title: 'Out of Memory Events Detected',
        description: `${data.oomEvents} OOM kill events detected. Pods are being terminated due to memory pressure, which can cause service disruptions and data loss.`,
        metric: 'oom_events',
        value: `${data.oomEvents} events`,
        suggestedActions: [
          'Review and increase memory limits for affected pods',
          'Analyze memory usage patterns and identify leaks',
          'Implement memory-aware autoscaling',
          'Consider vertical pod autoscaling (VPA)',
        ],
        tags: ['memory', 'oom', 'critical', 'resource'],
      });
    }

    // Security analizi
    if (data.securityEvents && data.securityEvents > 0) {
      const deniedRatio = (data.deniedEvents || 0) / data.securityEvents * 100;
      
      if (data.criticalCapabilities && data.criticalCapabilities > 0) {
        insights.push({
          id: `critical-caps-${now}`,
          type: 'anomaly',
          severity: 'critical',
          confidence: 0.95,
          title: 'Dangerous Linux Capabilities in Use',
          description: `${data.criticalCapabilities} workloads are using critical capabilities (SYS_ADMIN, SYS_MODULE, SYS_RAWIO). These capabilities grant near-root access and significantly increase security risk.`,
          metric: 'critical_capabilities',
          value: `${data.criticalCapabilities} workloads`,
          suggestedActions: [
            'Audit each workload using critical capabilities',
            'Apply principle of least privilege',
            'Consider using seccomp profiles to restrict syscalls',
            'Implement Pod Security Standards',
          ],
          tags: ['security', 'critical', 'capabilities'],
        });
      }

      if (deniedRatio > 20) {
        insights.push({
          id: `high-denial-rate-${now}`,
          type: 'anomaly',
          severity: 'high',
          confidence: 0.8,
          title: 'Elevated Security Denial Rate',
          description: `${deniedRatio.toFixed(0)}% of security events resulted in denials. This may indicate misconfigured policies, unauthorized access attempts, or application issues.`,
          metric: 'security_denial_rate',
          value: `${deniedRatio.toFixed(0)}%`,
          suggestedActions: [
            'Review security policy configurations',
            'Analyze denied events for patterns',
            'Check for potential security threats',
            'Update policies if denials are false positives',
          ],
          tags: ['security', 'policy', 'denial'],
        });
      }
    }

    // Change risk analizi
    if (data.criticalChanges && data.criticalChanges > 0) {
      insights.push({
        id: `critical-changes-${now}`,
        type: 'anomaly',
        severity: 'critical',
        confidence: 0.9,
        title: 'Critical Infrastructure Changes',
        description: `${data.criticalChanges} critical changes detected in your infrastructure. These changes have high impact potential and require immediate attention.`,
        metric: 'critical_changes',
        value: `${data.criticalChanges} changes`,
        suggestedActions: [
          'Review each critical change in detail',
          'Verify changes were authorized',
          'Monitor for any resulting issues',
          'Consider rollback if unexpected behavior occurs',
        ],
        tags: ['changes', 'critical', 'infrastructure'],
      });
    } else if (data.highRiskChanges && data.highRiskChanges > 0) {
      insights.push({
        id: `high-risk-changes-${now}`,
        type: 'anomaly',
        severity: 'high',
        confidence: 0.8,
        title: 'High-Risk Changes Detected',
        description: `${data.highRiskChanges} high-risk infrastructure changes identified. Monitor closely for any unexpected behavior.`,
        metric: 'high_risk_changes',
        value: `${data.highRiskChanges} changes`,
        suggestedActions: [
          'Review change impact analysis',
          'Monitor affected services',
          'Have rollback plan ready',
        ],
        tags: ['changes', 'high-risk', 'infrastructure'],
      });
    }

    // Workload health analizi
    if (data.totalWorkloads && data.totalWorkloads > 0) {
      const healthyRatio = ((data.activeWorkloads || 0) / data.totalWorkloads) * 100;
      
      if (healthyRatio < 90 && data.failedPods && data.failedPods > 0) {
        insights.push({
          id: `unhealthy-workloads-${now}`,
          type: 'anomaly',
          severity: healthyRatio < 70 ? 'critical' : 'high',
          confidence: 0.85,
          title: 'Workload Health Degraded',
          description: `Only ${healthyRatio.toFixed(0)}% of workloads are healthy. ${data.failedPods} pods are in failed state, indicating deployment or resource issues.`,
          metric: 'workload_health',
          value: `${healthyRatio.toFixed(0)}%`,
          suggestedActions: [
            'Check pod logs for failure reasons',
            'Review resource requests and limits',
            'Verify image pull and deployment configurations',
            'Check node health and capacity',
          ],
          tags: ['workload', 'health', 'pods'],
        });
      } else if (healthyRatio >= 99) {
        insights.push({
          id: `success-workloads-${now}`,
          type: 'recommendation',
          severity: 'info',
          confidence: 0.95,
          title: 'Excellent Workload Health',
          description: `${healthyRatio.toFixed(0)}% of workloads are running healthy (${data.activeWorkloads}/${data.totalWorkloads}). Your cluster is operating optimally.`,
          metric: 'workload_health',
          value: `${data.activeWorkloads}/${data.totalWorkloads}`,
          suggestedActions: ['Maintain current practices'],
          tags: ['workload', 'health', 'success'],
        });
      }
    }

    // Trend analizi (historical comparison)
    if (data.previousPeriod) {
      const prev = data.previousPeriod;

      // Error trend
      if (prev.totalErrors !== undefined && data.totalErrors !== undefined && prev.totalErrors > 0) {
        const errorChange = ((data.totalErrors - prev.totalErrors) / prev.totalErrors) * 100;
        
        if (errorChange > 50) {
          insights.push({
            id: `error-trend-increase-${now}`,
            type: 'trend',
            severity: errorChange > 100 ? 'critical' : 'high',
            confidence: 0.75,
            title: 'Error Rate Increasing Rapidly',
            description: `Errors have increased by ${errorChange.toFixed(0)}% compared to the previous period. This indicates a developing problem that needs investigation.`,
            metric: 'error_trend',
            value: `+${errorChange.toFixed(0)}%`,
            suggestedActions: [
              'Identify the source of new errors',
              'Check for recent deployments or configuration changes',
              'Review application logs and metrics',
            ],
            tags: ['trend', 'error', 'increasing'],
          });
        } else if (errorChange < -30) {
          insights.push({
            id: `error-trend-decrease-${now}`,
            type: 'trend',
            severity: 'info',
            confidence: 0.8,
            title: 'Error Rate Improving',
            description: `Errors have decreased by ${Math.abs(errorChange).toFixed(0)}% compared to the previous period. Your reliability efforts are showing results.`,
            metric: 'error_trend',
            value: `${errorChange.toFixed(0)}%`,
            suggestedActions: ['Continue monitoring to confirm sustained improvement'],
            tags: ['trend', 'error', 'improving'],
          });
        }
      }

      // Event volume trend
      if (prev.totalEvents && data.totalEvents) {
        const eventChange = ((data.totalEvents - prev.totalEvents) / prev.totalEvents) * 100;
        
        if (Math.abs(eventChange) > 50) {
          insights.push({
            id: `event-volume-trend-${now}`,
            type: 'trend',
            severity: eventChange > 100 ? 'high' : 'medium',
            confidence: 0.7,
            title: `Event Volume ${eventChange > 0 ? 'Spike' : 'Drop'}`,
            description: `Event volume has ${eventChange > 0 ? 'increased' : 'decreased'} by ${Math.abs(eventChange).toFixed(0)}% compared to the previous period. This may indicate ${eventChange > 0 ? 'increased activity or potential issues' : 'reduced activity or data collection problems'}.`,
            metric: 'event_volume',
            value: `${eventChange > 0 ? '+' : ''}${eventChange.toFixed(0)}%`,
            suggestedActions: eventChange > 0 
              ? ['Investigate the cause of increased activity', 'Verify system capacity']
              : ['Check for data collection issues', 'Verify service availability'],
            tags: ['trend', 'volume', eventChange > 0 ? 'increasing' : 'decreasing'],
          });
        }
      }
    }

    // Correlation-based insights
    if (data.avgLatencyMs && data.avgLatencyMs > 200 && data.totalErrors && data.totalErrors > 0) {
      insights.push({
        id: `correlation-latency-errors-${now}`,
        type: 'correlation',
        severity: 'medium',
        confidence: 0.7,
        title: 'Latency and Errors May Be Related',
        description: 'Both latency and error rates are elevated. High latency often leads to timeouts and errors. Addressing the latency issue may reduce errors.',
        suggestedActions: [
          'Focus on resolving latency issues first',
          'Check for resource contention',
          'Review timeout configurations',
        ],
        tags: ['correlation', 'latency', 'error'],
      });
    }

    // Healthy system check
    if (insights.length === 0 || insights.every(i => i.severity === 'info')) {
      insights.push(this.insightGenerator.createHealthySystemInsight());
    }

    // Sort by severity
    const severityOrder = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
    return insights.sort((a, b) => {
      const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
      if (severityDiff !== 0) return severityDiff;
      return b.confidence - a.confidence;
    });
  }
}

// Export singleton instance
export const insightEngine = new InsightEngine();

// Export utility functions
export { StatUtils };
