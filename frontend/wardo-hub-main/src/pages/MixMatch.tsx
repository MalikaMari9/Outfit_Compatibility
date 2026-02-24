import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, Upload, AlertCircle, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';
import { apiUrl, getAuthHeader } from '@/lib/api';

const MIXMATCH_LOADING_STAGES = [
  'Uploading image files...',
  'Analyzing compatibility...',
  'Generating style explanation...',
];

const MIXMATCH_FASHION_TIPS = [
  'Pair one statement piece with one minimal piece for cleaner balance.',
  'When both pieces are neutral, add contrast with shoes or accessories.',
  'If the top has texture or print, keep the bottom silhouette simple.',
  'Light-on-light looks cleaner when fabrics have slightly different textures.',
  'For wide bottoms, a more structured top usually improves proportion.',
  'Repeat one color tone across your outfit to look intentional.',
];

const formatElapsed = (ms: number): string => {
  const safeMs = Math.max(0, Math.floor(ms));
  const totalSec = Math.floor(safeMs / 1000);
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  const tenths = Math.floor((safeMs % 1000) / 100);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${tenths}`;
};

type MixMatchInputMode = 'two_piece' | 'full_body';
type ImageDims = { width: number; height: number };
type CropBox = [number, number, number, number];
type SplitFailure = {
  message: string;
  topReason: string;
  bottomReason: string;
};

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const numOr = (v: unknown, fallback = 0): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
};

const pct = (v: unknown): number => Math.round(numOr(v, 0) * 100);

const toLabel = (v: unknown): string => {
  const s = String(v || '').trim();
  return s ? s : 'Unknown';
};

const toList = (v: unknown): string[] => {
  if (Array.isArray(v)) return v.map((row) => String(row || '').trim()).filter(Boolean);
  const one = String(v || '').trim();
  return one ? [one] : [];
};

const patternType = (isPatterned: unknown, label: unknown): string => {
  if (typeof isPatterned === 'boolean' && !isPatterned) return 'Solid';
  const raw = String(label || '').trim();
  if (!raw) return 'Patterned';
  return raw.charAt(0).toUpperCase() + raw.slice(1);
};

const patternMeta = (isPatterned: unknown, prob: unknown): string => {
  if (typeof isPatterned === 'boolean' && !isPatterned) return 'No print';
  const p = pct(prob);
  return p > 0 ? `${p}% confidence` : 'Detected';
};

const toCropBox = (v: unknown): CropBox | null => {
  if (!Array.isArray(v) || v.length < 4) return null;
  const [x1Raw, y1Raw, x2Raw, y2Raw] = v;
  const x1 = Number(x1Raw);
  const y1 = Number(y1Raw);
  const x2 = Number(x2Raw);
  const y2 = Number(y2Raw);
  if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
  if (x2 <= x1 || y2 <= y1) return null;
  return [x1, y1, x2, y2];
};

const cropBoxStyle = (box: CropBox, dims: ImageDims): React.CSSProperties => {
  const [x1, y1, x2, y2] = box;
  const width = Math.max(1, dims.width);
  const height = Math.max(1, dims.height);
  const left = (x1 / width) * 100;
  const top = (y1 / height) * 100;
  const w = ((x2 - x1) / width) * 100;
  const h = ((y2 - y1) / height) * 100;
  return {
    position: 'absolute',
    left: `${Math.max(0, Math.min(100, left))}%`,
    top: `${Math.max(0, Math.min(100, top))}%`,
    width: `${Math.max(0, Math.min(100, w))}%`,
    height: `${Math.max(0, Math.min(100, h))}%`,
  };
};

const MixMatch = () => {
  const navigate = useNavigate();
  const [topImage, setTopImage] = useState<string | null>(null);
  const [bottomImage, setBottomImage] = useState<string | null>(null);
  const [topFile, setTopFile] = useState<File | null>(null);
  const [bottomFile, setBottomFile] = useState<File | null>(null);
  const [fullBodyImage, setFullBodyImage] = useState<string | null>(null);
  const [fullBodyFile, setFullBodyFile] = useState<File | null>(null);
  const [fullBodyDims, setFullBodyDims] = useState<ImageDims | null>(null);
  const [inputMode, setInputMode] = useState<MixMatchInputMode>('two_piece');
  const [showResults, setShowResults] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadingStageIndex, setLoadingStageIndex] = useState(0);
  const [loadingTipIndex, setLoadingTipIndex] = useState(0);
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [compatibilityResult, setCompatibilityResult] = useState<unknown>(null);
  const [isGeneratingExplanation, setIsGeneratingExplanation] = useState(false);
  const [splitFailure, setSplitFailure] = useState<SplitFailure | null>(null);
  const [reportMessage, setReportMessage] = useState('');
  const [reportDialogOpen, setReportDialogOpen] = useState(false);
  const { toast } = useToast();
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!isSubmitting) {
      setLoadingStageIndex(0);
      return;
    }
    setLoadingStageIndex(0);
    const timer = window.setInterval(() => {
      setLoadingStageIndex((prev) => Math.min(prev + 1, MIXMATCH_LOADING_STAGES.length - 1));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [isSubmitting]);

  useEffect(() => {
    if (!isSubmitting) {
      setLoadingTipIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingTipIndex((prev) => (prev + 1) % MIXMATCH_FASHION_TIPS.length);
    }, 2800);
    return () => window.clearInterval(timer);
  }, [isSubmitting]);

  useEffect(() => {
    if (!isSubmitting) {
      setLoadingElapsedMs(0);
      return;
    }
    const startedAt = Date.now();
    setLoadingElapsedMs(0);
    const timer = window.setInterval(() => {
      setLoadingElapsedMs(Date.now() - startedAt);
    }, 100);
    return () => window.clearInterval(timer);
  }, [isSubmitting]);

  const handleImageUpload = (type: 'top' | 'bottom' | 'full_body') => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_UPLOAD_BYTES) {
      toast({
        variant: 'destructive',
        title: 'Image Too Large',
        description: 'Please upload images smaller than 10 MB.',
      });
      return;
    }

    const reader = new FileReader();
    reader.onloadend = () => {
      if (type === 'top') {
        setTopImage(reader.result as string);
        setTopFile(file);
      } else if (type === 'bottom') {
        setBottomImage(reader.result as string);
        setBottomFile(file);
      } else {
        const resultUrl = reader.result as string;
        setFullBodyImage(resultUrl);
        setFullBodyFile(file);
        const img = new Image();
        img.onload = () => {
          setFullBodyDims({
            width: img.naturalWidth || img.width || 0,
            height: img.naturalHeight || img.height || 0,
          });
        };
        img.onerror = () => setFullBodyDims(null);
        img.src = resultUrl;
      }
    };
    reader.readAsDataURL(file);
  };

  const resetMixMatch = () => {
    requestTokenRef.current += 1;
    setShowResults(false);
    setTopImage(null);
    setBottomImage(null);
    setTopFile(null);
    setBottomFile(null);
    setFullBodyImage(null);
    setFullBodyFile(null);
    setFullBodyDims(null);
    setCompatibilityResult(null);
    setIsGeneratingExplanation(false);
    setSplitFailure(null);
    setReportMessage('');
    setReportDialogOpen(false);
  };

  const handleAnalyze = async () => {
    if (inputMode === 'two_piece' && (!topFile || !bottomFile)) {
      toast({
        variant: 'destructive',
        title: 'Missing Images',
        description: 'Please upload both a top and bottom image.',
      });
      return;
    }
    if (inputMode === 'full_body' && !fullBodyFile) {
      toast({
        variant: 'destructive',
        title: 'Missing Image',
        description: 'Please upload one full-body image for auto split.',
      });
      return;
    }

    const requestToken = ++requestTokenRef.current;
    setIsSubmitting(true);
    setSplitFailure(null);

    try {
      const formData = new FormData();
      formData.append('input_mode', inputMode);
      if (inputMode === 'two_piece') {
        formData.append('top', topFile as File);
        formData.append('bottom', bottomFile as File);
      } else {
        formData.append('full_body', fullBodyFile as File);
      }

      const response = await fetch(apiUrl('/compatibility'), {
        method: 'POST',
        headers: { ...getAuthHeader() },
        body: formData,
      });

      const data = await response.json().catch(() => ({}));
      const payload = (data || {}) as Record<string, any>;

      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('token');
          toast({
            variant: 'destructive',
            title: 'Session Expired',
            description: 'Please log in again.',
          });
          navigate('/auth');
          return;
        }
        const message = data?.message || data?.error || 'Compatibility request failed.';
        if (payload?.code === 'FULL_BODY_SPLIT_FAILED') {
          const gate = (payload?.details?.split_gate || {}) as Record<string, any>;
          setSplitFailure({
            message,
            topReason: String(gate?.top_reason || 'unknown'),
            bottomReason: String(gate?.bottom_reason || 'unknown'),
          });
        }
        toast({
          variant: 'destructive',
          title: payload?.code === 'FULL_BODY_SPLIT_FAILED' ? 'Full-Body Split Failed' : 'Compatibility Failed',
          description: message,
        });
        return;
      }

      setCompatibilityResult(payload);
      setShowResults(true);
      void fetchExplanationAsync(payload, requestToken);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Compatibility Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const buildPairFacts = (payload: Record<string, any>): Record<string, unknown> => {
    const d = (payload?.details || {}) as Record<string, any>;
    const b = (payload?.breakdown || {}) as Record<string, any>;
    return {
      top_image: String(payload?.top_image || ''),
      bottom_image: String(payload?.bottom_image || ''),
      label: String(payload?.label || ''),
      final_score: numOr(payload?.final_score, 0),
      breakdown: {
        model: numOr(b?.model, 0),
        type_prior: numOr(b?.type_prior, 0),
        color: numOr(b?.color, 0),
        brightness: numOr(b?.brightness, 0),
        pattern: numOr(b?.pattern, 0),
      },
      thresholds: {
        weak: numOr(d?.weak_threshold, 0.45),
        borderline: numOr(d?.borderline_threshold, 0.55),
        good: numOr(d?.good_threshold ?? d?.threshold, 0.62),
        excellent: numOr(d?.excellent_threshold, 0.72),
      },
      metadata: {
        top_category_name: String(d?.top_category || ''),
        bottom_category_name: String(d?.bottom_category || ''),
        top_primary_color: String(d?.top_primary_color || ''),
        bottom_primary_color: String(d?.bottom_primary_color || ''),
        top_pattern_name: patternType(d?.top_is_patterned, d?.top_pattern_label),
        bottom_pattern_name: patternType(d?.bottom_is_patterned, d?.bottom_pattern_label),
        top_pattern_prob: numOr(d?.top_pattern_prob, 0),
        bottom_pattern_prob: numOr(d?.bottom_pattern_prob, 0),
        top_category_source: String(d?.top_category_source || ''),
        bottom_category_source: String(d?.bottom_category_source || ''),
        top_mask_fallback: Boolean(d?.top_mask_fallback),
        bottom_mask_fallback: Boolean(d?.bottom_mask_fallback),
        top_autocrop_reason: String(d?.top_autocrop?.reason || ''),
        bottom_autocrop_reason: String(d?.bottom_autocrop?.reason || ''),
      },
    };
  };

  const updatePairExplanationState = (
    payload: Record<string, any>,
    requestToken: number,
    llmPatch: {
      llm_status: string;
      llm_source?: string;
      llm_cached?: boolean;
      llm_explanation?: unknown;
    },
  ) => {
    if (requestToken !== requestTokenRef.current) return;
    setCompatibilityResult((prev) => {
      const base = (prev && typeof prev === 'object' ? prev : payload) as Record<string, any>;
      const nextDetails: Record<string, any> = { ...(base.details || {}) };
      nextDetails.llm_status = String(llmPatch.llm_status || 'unavailable');
      nextDetails.llm_source = String(llmPatch.llm_source || '');
      nextDetails.llm_cached = Boolean(llmPatch.llm_cached || false);
      if (llmPatch.llm_explanation !== undefined) nextDetails.llm_explanation = llmPatch.llm_explanation;
      return {
        ...base,
        details: nextDetails,
      };
    });
  };

  const fetchExplanationAsync = async (payload: Record<string, any>, requestToken: number) => {
    setIsGeneratingExplanation(true);
    try {
      const facts = buildPairFacts(payload);
      const response = await fetch(apiUrl('/explain'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({ facts }),
      });
      const llmData = (await response.json().catch(() => ({}))) as Record<string, any>;
      if (!response.ok) {
        if (response.status === 401) {
          localStorage.removeItem('token');
          toast({
            variant: 'destructive',
            title: 'Session Expired',
            description: 'Please log in again.',
          });
          navigate('/auth');
        }
        updatePairExplanationState(payload, requestToken, {
          llm_status: 'unavailable',
          llm_source: 'none',
          llm_cached: false,
        });
        return;
      }
      updatePairExplanationState(payload, requestToken, {
        llm_status: String(llmData?.llm_status || (llmData?.llm_explanation ? 'ok' : 'unavailable')),
        llm_source: String(llmData?.llm_source || ''),
        llm_cached: Boolean(llmData?.llm_cached || false),
        llm_explanation: llmData?.llm_explanation,
      });
    } catch (error) {
      updatePairExplanationState(payload, requestToken, {
        llm_status: 'unavailable',
        llm_source: 'none',
        llm_cached: false,
      });
    } finally {
      if (requestToken === requestTokenRef.current) {
        setIsGeneratingExplanation(false);
      }
    }
  };

  const handleReport = async () => {
    const message = reportMessage.trim();
    if (!message) {
      toast({
        variant: 'destructive',
        title: 'Missing Message',
        description: 'Please describe the issue before submitting.',
      });
      return;
    }
    try {
      await fetch(apiUrl('/feedback'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({
          page: 'mixmatch',
          message,
        }),
      });

      toast({
        title: 'Report Submitted',
        description: 'Your report has been sent to the admin for review.',
      });
      setReportMessage('');
      setReportDialogOpen(false);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Report Failed',
        description: 'Network error. Please try again.',
      });
    }
  };

  const resultPayload =
    compatibilityResult && typeof compatibilityResult === 'object'
      ? (compatibilityResult as Record<string, any>)
      : null;
  const resultDetails = (resultPayload?.details || {}) as Record<string, any>;
  const resultBreakdown = (resultPayload?.breakdown || {}) as Record<string, any>;
  const llmExplanation =
    resultDetails?.llm_explanation && typeof resultDetails.llm_explanation === 'object'
      ? (resultDetails.llm_explanation as Record<string, any>)
      : null;
  const llmWhy = toList(llmExplanation?.why_it_works);
  const llmRisks = toList(llmExplanation?.risk_points);
  const llmSuggestion = toList(llmExplanation?.style_suggestion);
  const llmStatus = String(resultDetails?.llm_status || 'deferred');
  const llmSource = String(resultDetails?.llm_source || '');
  const llmStatusLabel =
    isGeneratingExplanation || llmStatus === 'deferred'
      ? 'Generating...'
      : llmStatus === 'fallback' || llmSource === 'fallback'
        ? 'Quick Analysis'
        : llmStatus === 'ok'
          ? 'AI Stylist'
          : 'Unavailable';
  const llmBadgeVariant =
    isGeneratingExplanation || llmStatus === 'deferred'
      ? 'outline'
      : llmStatus === 'ok'
        ? 'default'
        : llmStatus === 'fallback'
          ? 'secondary'
          : 'outline';
  const finalScore = numOr(resultPayload?.final_score, 0);
  const finalScorePct = pct(finalScore);
  const scoreTone =
    finalScore >= 0.72
      ? 'text-emerald-600'
      : finalScore >= 0.62
        ? 'text-green-600'
        : finalScore >= 0.55
          ? 'text-amber-600'
          : finalScore >= 0.45
            ? 'text-orange-600'
            : 'text-red-600';
  const componentScores = [
    { label: 'Model Fit', value: pct(resultBreakdown?.model) },
    { label: 'Type Match', value: pct(resultBreakdown?.type_prior) },
    { label: 'Color Harmony', value: pct(resultBreakdown?.color) },
    { label: 'Brightness Balance', value: pct(resultBreakdown?.brightness) },
    { label: 'Pattern Balance', value: pct(resultBreakdown?.pattern) },
  ];
  const topPatternType = patternType(resultDetails?.top_is_patterned, resultDetails?.top_pattern_label);
  const bottomPatternType = patternType(resultDetails?.bottom_is_patterned, resultDetails?.bottom_pattern_label);
  const patternPairing = `${topPatternType} + ${bottomPatternType}`;
  const resultInputMode = String(resultDetails?.input_mode || '').trim().toLowerCase();
  const splitStatus = String(resultDetails?.split_status || '').trim().toLowerCase();
  const topAutoCropBox = toCropBox(resultDetails?.top_autocrop?.crop_box);
  const bottomAutoCropBox = toCropBox(resultDetails?.bottom_autocrop?.crop_box);
  const resultInputModeLabel =
    resultInputMode === 'full_body_auto_split'
      ? 'Full-body auto split'
      : resultInputMode === 'two_piece'
        ? 'Two-piece upload'
        : '';
  const canShowSplitPreview =
    resultInputMode === 'full_body_auto_split' &&
    splitStatus === 'ok' &&
    Boolean(fullBodyImage) &&
    Boolean(fullBodyDims) &&
    Boolean(topAutoCropBox || bottomAutoCropBox);
  const loadingStage = MIXMATCH_LOADING_STAGES[Math.min(loadingStageIndex, MIXMATCH_LOADING_STAGES.length - 1)];
  const loadingPct = Math.round(
    ((Math.min(loadingStageIndex, MIXMATCH_LOADING_STAGES.length - 1) + 1) / MIXMATCH_LOADING_STAGES.length) * 100,
  );
  const loadingTip = MIXMATCH_FASHION_TIPS[loadingTipIndex % MIXMATCH_FASHION_TIPS.length];
  const loadingElapsed = formatElapsed(loadingElapsedMs);

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />
      {isSubmitting && (
        <div className="fixed inset-0 z-[120] bg-background/85 backdrop-blur-sm" aria-live="polite">
          <div className="flex h-full items-center justify-center px-4">
            <div className="w-full max-w-xl rounded-2xl border border-border bg-card p-6 shadow-2xl">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">Analyzing Outfit</p>
              <div className="mt-3 flex items-center gap-2" aria-hidden="true">
                <span
                  className="h-2.5 w-2.5 rounded-full bg-primary animate-bounce"
                  style={{ animationDelay: '0ms' }}
                />
                <span
                  className="h-2.5 w-2.5 rounded-full bg-primary animate-bounce"
                  style={{ animationDelay: '140ms' }}
                />
                <span
                  className="h-2.5 w-2.5 rounded-full bg-primary animate-bounce"
                  style={{ animationDelay: '280ms' }}
                />
              </div>
              <div className="mt-4 flex items-center justify-between text-sm">
                <span className="font-medium">{loadingStage}</span>
                <span className="text-muted-foreground">{loadingPct}%</span>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Debug timer: <span className="font-mono">{loadingElapsed}</span>
              </p>
              <div className="mt-4 rounded-lg border border-border bg-secondary/40 p-3">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Style tip</p>
                <p className="mt-1 text-sm">{loadingTip}</p>
              </div>
            </div>
          </div>
        </div>
      )}
      <main className="container mx-auto px-4 py-8 flex-1">
        <Link
          to="/style-studio"
          className="inline-flex items-center text-muted-foreground hover:text-foreground mb-6"
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to Style Studio
        </Link>

        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-8">
            <h1 className="text-4xl font-playfair font-bold mb-4">Mix & Match</h1>
            <p className="text-muted-foreground">
              Compare two-piece uploads or use full-body auto split to test compatibility.
            </p>
          </div>

	          <Card className="border-none shadow-lg">
	            <CardContent className="p-8">
                {!showResults ? (
                  <>
	              <div className="mb-6 grid grid-cols-1 gap-2 sm:grid-cols-2">
	                <Button
	                  type="button"
	                  variant={inputMode === 'two_piece' ? 'default' : 'outline'}
                  onClick={() => {
                    setInputMode('two_piece');
                    setSplitFailure(null);
                    setFullBodyImage(null);
                    setFullBodyFile(null);
                    setFullBodyDims(null);
                  }}
                >
                  Two-Piece Upload
                </Button>
                <Button
                  type="button"
                  variant={inputMode === 'full_body' ? 'default' : 'outline'}
                  onClick={() => {
                    setInputMode('full_body');
                    setSplitFailure(null);
                    setTopImage(null);
                    setBottomImage(null);
                    setTopFile(null);
                    setBottomFile(null);
                  }}
                >
                  Full-Body Auto Split
                </Button>
              </div>
              <p className="mb-6 text-xs text-muted-foreground">
                {inputMode === 'two_piece'
                  ? 'Upload one top and one bottom image.'
                  : 'Upload one full-body image. We will auto-crop top and bottom using YOLO pose; if split confidence is low, we will ask for separate uploads.'}
              </p>

              {inputMode === 'two_piece' ? (
                <div className="grid md:grid-cols-2 gap-8 mb-8">
                  {/* Top Upload */}
                  <div>
                    <p className="text-sm font-medium text-center mb-3">Top Piece</p>
                    <div className="border-2 border-dashed border-border rounded-xl p-6 text-center bg-secondary/30 min-h-[250px] flex items-center justify-center">
                      {topImage ? (
                        <div className="relative w-full">
                          <img
                            src={topImage}
                            alt="Top piece"
                            className="max-h-48 mx-auto rounded-lg object-cover"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            className="mt-3"
                            onClick={() => {
                              setTopImage(null);
                              setTopFile(null);
                            }}
                          >
                            Remove
                          </Button>
                        </div>
                      ) : (
                        <label className="cursor-pointer block w-full">
                          <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                          <p className="text-muted-foreground text-sm mb-1">Upload Top</p>
                          <p className="text-xs text-muted-foreground">
                            Shirt, blouse, jacket, etc.
                          </p>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={handleImageUpload('top')}
                            className="hidden"
                          />
                        </label>
                      )}
                    </div>
                  </div>

                  {/* Bottom Upload */}
                  <div>
                    <p className="text-sm font-medium text-center mb-3">Bottom Piece</p>
                    <div className="border-2 border-dashed border-border rounded-xl p-6 text-center bg-secondary/30 min-h-[250px] flex items-center justify-center">
                      {bottomImage ? (
                        <div className="relative w-full">
                          <img
                            src={bottomImage}
                            alt="Bottom piece"
                            className="max-h-48 mx-auto rounded-lg object-cover"
                          />
                          <Button
                            variant="outline"
                            size="sm"
                            className="mt-3"
                            onClick={() => {
                              setBottomImage(null);
                              setBottomFile(null);
                            }}
                          >
                            Remove
                          </Button>
                        </div>
                      ) : (
                        <label className="cursor-pointer block w-full">
                          <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                          <p className="text-muted-foreground text-sm mb-1">Upload Bottom</p>
                          <p className="text-xs text-muted-foreground">
                            Pants, skirt, shorts, etc.
                          </p>
                          <input
                            type="file"
                            accept="image/*"
                            onChange={handleImageUpload('bottom')}
                            className="hidden"
                          />
                        </label>
                      )}
                    </div>
                  </div>
                </div>
              ) : (
                <div className="mb-8">
                  <p className="text-sm font-medium text-center mb-3">Full-Body Image</p>
                  <div className="border-2 border-dashed border-border rounded-xl p-6 text-center bg-secondary/30 min-h-[250px] flex items-center justify-center">
                    {fullBodyImage ? (
                      <div className="relative w-full">
                        <img
                          src={fullBodyImage}
                          alt="Full-body input"
                          className="max-h-56 mx-auto rounded-lg object-cover"
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          className="mt-3"
                          onClick={() => {
                            setFullBodyImage(null);
                            setFullBodyFile(null);
                            setFullBodyDims(null);
                          }}
                        >
                          Remove
                        </Button>
                      </div>
                    ) : (
                      <label className="cursor-pointer block w-full">
                        <Upload className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
                        <p className="text-muted-foreground text-sm mb-1">Upload Full Body</p>
                        <p className="text-xs text-muted-foreground">
                          Person image showing both upper and lower clothing.
                        </p>
                        <input
                          type="file"
                          accept="image/*"
                          onChange={handleImageUpload('full_body')}
                          className="hidden"
                        />
                      </label>
	                    )}
	                  </div>
	                </div>
	              )}
	                <div className="space-y-4">
	                    {inputMode === 'full_body' && splitFailure && (
	                      <div className="rounded-lg border border-orange-300 bg-orange-50 p-4 text-sm">
	                        <p className="font-medium text-orange-900">{splitFailure.message}</p>
                        <p className="mt-2 text-orange-800">
                          Top split reason: <span className="font-semibold">{toLabel(splitFailure.topReason)}</span>
                        </p>
                        <p className="text-orange-800">
                          Bottom split reason: <span className="font-semibold">{toLabel(splitFailure.bottomReason)}</span>
                        </p>
                        <div className="mt-3">
                          <Button
                            type="button"
                            variant="outline"
                            onClick={() => {
                              setInputMode('two_piece');
                              setSplitFailure(null);
                              setFullBodyImage(null);
                              setFullBodyFile(null);
                              setFullBodyDims(null);
                            }}
                          >
                            Switch to Two-Piece Upload
                          </Button>
                        </div>
                      </div>
	                    )}
				                  <Button onClick={handleAnalyze} className="w-full" size="lg" disabled={isSubmitting}>
				                    {isSubmitting ? 'Processing...' : 'Analyze Compatibility'}
				                  </Button>
			                </div>
                  </>
		              ) : (
				                <div className="space-y-8">
                    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-end">
                      <Button
                        variant="outline"
                        className="w-full sm:flex-1"
                        onClick={resetMixMatch}
                      >
                        Try Another Combination
                      </Button>
                      <Dialog open={reportDialogOpen} onOpenChange={setReportDialogOpen}>
                        <DialogTrigger asChild>
                          <Button
                            variant="ghost"
                            className="text-destructive hover:text-destructive hover:bg-destructive/10"
                          >
                            <AlertCircle className="h-4 w-4 mr-2" />
                            Report Issue
                          </Button>
                        </DialogTrigger>
                        <DialogContent className="bg-card">
                          <DialogHeader>
                            <DialogTitle>Report an Issue</DialogTitle>
                          </DialogHeader>
                          <div className="space-y-4 pt-2">
                            <div className="space-y-2">
                              <Label htmlFor="mixmatch-report-message">Describe the issue</Label>
                              <Textarea
                                id="mixmatch-report-message"
                                placeholder="Tell us what went wrong..."
                                rows={4}
                                value={reportMessage}
                                onChange={(e) => setReportMessage(e.target.value)}
                              />
                            </div>
                            <Button
                              className="w-full"
                              onClick={handleReport}
                              disabled={!reportMessage.trim()}
                            >
                              Submit Report
                            </Button>
                          </div>
                        </DialogContent>
                      </Dialog>
                    </div>

                    <div className="grid md:grid-cols-2 gap-8">
                      <Card className="border-0 shadow-lg overflow-hidden">
                        <CardHeader className="bg-secondary/50">
                          <CardTitle className="font-serif text-lg">Analyzed Input</CardTitle>
                        </CardHeader>
                        <CardContent className="p-5 space-y-4">
                          {resultInputMode === 'two_piece' ? (
                            <div className="grid gap-4 sm:grid-cols-2">
                              <div className="rounded-lg border border-border bg-background p-3">
                                <p className="text-xs uppercase text-muted-foreground">Top Upload</p>
                                {topImage ? (
                                  <img
                                    src={topImage}
                                    alt="Uploaded top"
                                    className="mt-2 max-h-56 w-full rounded-lg object-contain"
                                  />
                                ) : (
                                  <p className="mt-2 text-xs text-muted-foreground">No top preview available.</p>
                                )}
                              </div>
                              <div className="rounded-lg border border-border bg-background p-3">
                                <p className="text-xs uppercase text-muted-foreground">Bottom Upload</p>
                                {bottomImage ? (
                                  <img
                                    src={bottomImage}
                                    alt="Uploaded bottom"
                                    className="mt-2 max-h-56 w-full rounded-lg object-contain"
                                  />
                                ) : (
                                  <p className="mt-2 text-xs text-muted-foreground">No bottom preview available.</p>
                                )}
                              </div>
                            </div>
                          ) : (
                            <div className="rounded-lg border border-border bg-background p-3">
                              <p className="text-xs uppercase text-muted-foreground">Full-Body Upload</p>
                              {fullBodyImage ? (
                                <img
                                  src={fullBodyImage}
                                  alt="Full-body upload"
                                  className="mt-2 max-h-72 w-full rounded-lg object-contain"
                                />
                              ) : (
                                <p className="mt-2 text-xs text-muted-foreground">No full-body preview available.</p>
                              )}
                            </div>
                          )}
                          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-sm">
                            <p className="text-xs uppercase text-muted-foreground">Detected Pair</p>
                            <p className="mt-1 font-semibold">
                              {toLabel(resultDetails?.top_category)} + {toLabel(resultDetails?.bottom_category)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Colors: {toLabel(resultDetails?.top_primary_color)} + {toLabel(resultDetails?.bottom_primary_color)}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Patterns: {topPatternType} + {bottomPatternType}
                            </p>
                          </div>
                        </CardContent>
                      </Card>

                      <Card className="border-0 shadow-lg overflow-hidden">
                        <CardHeader className="bg-primary/10">
                          <CardTitle className="font-serif text-lg flex items-center gap-2">
                            <Sparkles className="h-5 w-5 text-primary" />
                            Compatibility Result
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="p-5 space-y-4">
                          <div className="flex items-start justify-between gap-3">
                            <div>
                              <p className={`text-3xl font-semibold ${scoreTone}`}>{finalScorePct}%</p>
                              <p className="text-sm text-muted-foreground">Final compatibility score</p>
                            </div>
                            <Badge variant="secondary">{toLabel(resultPayload?.label)}</Badge>
                          </div>
                          <div className="rounded-lg border border-border bg-secondary/30 p-3 text-sm">
                            <p className="text-xs uppercase text-muted-foreground">Pair Summary</p>
                            <p className="mt-1 font-semibold">
                              {toLabel(resultDetails?.top_category)} + {toLabel(resultDetails?.bottom_category)}
                            </p>
                            <p className="text-xs text-muted-foreground">Top color: {toLabel(resultDetails?.top_primary_color)}</p>
                            <p className="text-xs text-muted-foreground">Bottom color: {toLabel(resultDetails?.bottom_primary_color)}</p>
                            <p className="text-xs text-muted-foreground">Top pattern: {topPatternType} | {patternMeta(resultDetails?.top_is_patterned, resultDetails?.top_pattern_prob)}</p>
                            <p className="text-xs text-muted-foreground">Bottom pattern: {bottomPatternType} | {patternMeta(resultDetails?.bottom_is_patterned, resultDetails?.bottom_pattern_prob)}</p>
                          </div>
                          <p className="text-xs text-muted-foreground">Pattern pairing: {patternPairing}</p>
                          {resultInputModeLabel && (
                            <p className="text-xs text-muted-foreground">Input mode: {resultInputModeLabel}</p>
                          )}
                          {resultInputMode === 'full_body_auto_split' && splitStatus && (
                            <p className="text-xs text-muted-foreground">Split status: {toLabel(splitStatus)}</p>
                          )}
                        </CardContent>
                      </Card>
                    </div>

                    <Card className="border-0 shadow-lg">
                      <CardHeader className="bg-secondary/50">
                        <CardTitle className="font-serif text-lg flex items-center justify-between">
                          <span>Style Explanation</span>
                          <Badge variant={llmBadgeVariant}>{llmStatusLabel}</Badge>
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="p-5">
                        {isGeneratingExplanation && (
                          <div className="mb-3 rounded-lg border border-border bg-background/60 p-3">
                            <div className="flex items-center gap-2 text-sm">
                              <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
                              <span className="h-2 w-2 rounded-full bg-primary/80 animate-pulse [animation-delay:120ms]" />
                              <span className="h-2 w-2 rounded-full bg-primary/60 animate-pulse [animation-delay:240ms]" />
                              <span className="text-muted-foreground">AI stylist is writing your explanation...</span>
                            </div>
                            {!llmExplanation && (
                              <div className="mt-3 space-y-2">
                                <div className="h-3 w-5/6 rounded bg-secondary/70 animate-pulse" />
                                <div className="h-3 w-4/6 rounded bg-secondary/70 animate-pulse" />
                                <div className="h-3 w-3/6 rounded bg-secondary/70 animate-pulse" />
                              </div>
                            )}
                          </div>
                        )}
                        {llmExplanation ? (
                          <div className="space-y-3 text-sm">
                            <p className="text-muted-foreground">{toLabel(llmExplanation?.summary)}</p>
                            {llmWhy.length > 0 && (
                              <div>
                                <p className="font-medium">Why it works</p>
                                <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
                                  {llmWhy.map((row, idx) => (
                                    <li key={`why-${idx}`}>{row}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {llmRisks.length > 0 && (
                              <div>
                                <p className="font-medium">Risk points</p>
                                <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
                                  {llmRisks.map((row, idx) => (
                                    <li key={`risk-${idx}`}>{row}</li>
                                  ))}
                                </ul>
                              </div>
                            )}
                            {String(llmExplanation?.style_suggestion || '').trim() && (
                              <div>
                                <p className="font-medium">Suggestion</p>
                                {llmSuggestion.length <= 1 ? (
                                  <p className="text-muted-foreground">{llmSuggestion[0] || ''}</p>
                                ) : (
                                  <ul className="mt-1 list-disc space-y-1 pl-5 text-muted-foreground">
                                    {llmSuggestion.map((row, idx) => (
                                      <li key={`suggest-${idx}`}>{row}</li>
                                    ))}
                                  </ul>
                                )}
                              </div>
                            )}
                          </div>
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            {isGeneratingExplanation || llmStatus === 'deferred'
                              ? 'Generating explanation in the background...'
                              : llmStatus === 'fallback'
                                ? 'Using a quick deterministic explanation while AI stylist output is unavailable.'
                                : 'Explanation is unavailable for this request.'}
                          </p>
                        )}
                      </CardContent>
                    </Card>

                    <Card className="border-0 shadow-lg">
                      <CardHeader className="bg-secondary/50">
                        <CardTitle className="font-serif text-lg">Score Breakdown</CardTitle>
                      </CardHeader>
                      <CardContent className="p-5">
                        <div className="space-y-3">
                          {componentScores.map((row) => (
                            <div key={row.label}>
                              <div className="mb-1 flex items-center justify-between text-sm">
                                <span>{row.label}</span>
                                <span className="text-muted-foreground">{row.value}%</span>
                              </div>
                              <Progress value={row.value} />
                            </div>
                          ))}
                        </div>
                      </CardContent>
                    </Card>

                    {canShowSplitPreview && fullBodyImage && fullBodyDims && (
                      <Card className="border-0 shadow-lg">
                        <CardHeader className="bg-secondary/50">
                          <CardTitle className="font-serif text-lg">Full-Body Auto Split Preview</CardTitle>
                        </CardHeader>
                        <CardContent className="p-5">
                          <p className="text-xs text-muted-foreground">
                            Green box: Top crop. Orange box: Bottom crop.
                          </p>
                          <div className="mt-4 flex justify-center">
                            <div className="relative inline-block max-w-full overflow-hidden rounded-lg border border-border bg-background">
                              <img
                                src={fullBodyImage}
                                alt="Full-body split preview"
                                className="block max-h-[440px] w-auto object-contain"
                              />
                              {topAutoCropBox && (
                                <div
                                  style={cropBoxStyle(topAutoCropBox, fullBodyDims)}
                                  className="pointer-events-none border-2 border-emerald-500"
                                >
                                  <span className="absolute left-0 top-0 bg-emerald-600 px-1.5 py-0.5 text-[10px] font-medium text-white">
                                    Top
                                  </span>
                                </div>
                              )}
                              {bottomAutoCropBox && (
                                <div
                                  style={cropBoxStyle(bottomAutoCropBox, fullBodyDims)}
                                  className="pointer-events-none border-2 border-orange-500"
                                >
                                  <span className="absolute left-0 top-0 bg-orange-600 px-1.5 py-0.5 text-[10px] font-medium text-white">
                                    Bottom
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )}
		                </div>
		              )}
            </CardContent>
          </Card>
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default MixMatch;
