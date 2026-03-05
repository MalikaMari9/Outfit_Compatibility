import { useEffect, useRef, useState } from "react";
import { Upload, Sparkles, AlertTriangle, ArrowLeft, ChevronDown } from "lucide-react";
import { Link, useNavigate } from 'react-router-dom';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useToast } from '@/hooks/use-toast';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';
import { apiUrl, getAuthHeader } from '@/lib/api';
import { clearAuthState } from '@/lib/auth';

const GLOWUP_LOADING_STAGES = [
  "Uploading image...",
  "Analyzing outfit recommendation...",
  "Generating style explanation...",
];

const GLOWUP_FASHION_TIPS = [
  "Use one hero piece and keep the rest clean to avoid visual clutter.",
  "Monochrome outfits look sharper when materials are mixed.",
  "If your outfit feels flat, introduce one accent color through accessories.",
  "Balance oversized pieces with one fitted piece for better proportion.",
  "Keep prints and textures to one focal area for easier styling.",
  "A clear waistline often improves overall silhouette and polish.",
];

const formatElapsed = (ms: number): string => {
  const safeMs = Math.max(0, Math.floor(ms));
  const totalSec = Math.floor(safeMs / 1000);
  const minutes = Math.floor(totalSec / 60);
  const seconds = totalSec % 60;
  const tenths = Math.floor((safeMs % 1000) / 100);
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${tenths}`;
};

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

const scoreLabelFromThresholds = (
  score: number,
  thresholds?: {
    good?: unknown;
    borderline?: unknown;
    weak?: unknown;
    excellent?: unknown;
  },
): string => {
  const excellent = numOr(thresholds?.excellent, 0.72);
  const good = numOr(thresholds?.good, 0.62);
  const borderline = numOr(thresholds?.borderline, 0.55);
  const weak = numOr(thresholds?.weak, 0.45);
  if (score >= excellent) return 'Excellent Match';
  if (score >= good) return 'Good Match';
  if (score >= borderline) return 'Borderline Acceptable';
  if (score >= weak) return 'Weak Match';
  return 'Mismatch';
};

const normalizeRecommendationSource = (row: Record<string, any>): 'wardrobe' | 'polyvore' => {
  const imageUrl = String(row?.image_url || '').trim().toLowerCase();
  if (imageUrl.startsWith('/uploads')) return 'wardrobe';
  if (imageUrl.startsWith('/pipeline-autocrop') || imageUrl.startsWith('/catalog-images')) {
    return 'polyvore';
  }
  const raw = String(row?.source || '').trim().toLowerCase();
  if (raw === 'wardrobe') return 'wardrobe';
  if (raw === 'polyvore') return 'polyvore';
  return 'polyvore';
};

type GlowUpAnalysisMode = 'quick' | 'best';

const GLOWUP_MODE_CONFIG: Record<
  GlowUpAnalysisMode,
  {
    label: string;
    helper: string;
    topK: number;
    shortlistK: number;
    fastMode: boolean;
  }
> = {
  quick: {
    label: 'Quick',
    helper: 'Lower latency. Uses fast ranking and a smaller rerank pass.',
    topK: 4,
    shortlistK: 25,
    fastMode: true,
  },
  best: {
    label: 'Best',
    helper: 'Higher quality. Runs slower, but uses fuller ranking and richer checks.',
    topK: 4,
    shortlistK: 50,
    fastMode: false,
  },
};

const DEFAULT_GLOWUP_MODE: GlowUpAnalysisMode = 'quick';

const GlowUp = () => {
  const navigate = useNavigate();
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [loadingStageIndex, setLoadingStageIndex] = useState(0);
  const [loadingTipIndex, setLoadingTipIndex] = useState(0);
  const [loadingElapsedMs, setLoadingElapsedMs] = useState(0);
  const [showResults, setShowResults] = useState(false);
  const [recommendResult, setRecommendResult] = useState<unknown>(null);
  const [showPolyvoreRefs, setShowPolyvoreRefs] = useState(false);
  const [isGeneratingExplanation, setIsGeneratingExplanation] = useState(false);
  const [includePolyvoreRequested, setIncludePolyvoreRequested] = useState(true);
  const [reportMessage, setReportMessage] = useState('');
  const { toast } = useToast();
  const requestTokenRef = useRef(0);

  useEffect(() => {
    if (!isAnalyzing) {
      setLoadingStageIndex(0);
      return;
    }
    setLoadingStageIndex(0);
    const timer = window.setInterval(() => {
      setLoadingStageIndex((prev) => Math.min(prev + 1, GLOWUP_LOADING_STAGES.length - 1));
    }, 2500);
    return () => window.clearInterval(timer);
  }, [isAnalyzing]);

  useEffect(() => {
    if (!isAnalyzing) {
      setLoadingTipIndex(0);
      return;
    }
    const timer = window.setInterval(() => {
      setLoadingTipIndex((prev) => (prev + 1) % GLOWUP_FASHION_TIPS.length);
    }, 2800);
    return () => window.clearInterval(timer);
  }, [isAnalyzing]);

  useEffect(() => {
    if (!isAnalyzing) {
      setLoadingElapsedMs(0);
      return;
    }
    const startedAt = Date.now();
    setLoadingElapsedMs(0);
    const timer = window.setInterval(() => {
      setLoadingElapsedMs(Date.now() - startedAt);
    }, 100);
    return () => window.clearInterval(timer);
  }, [isAnalyzing]);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = () => {
      setUploadedImage(reader.result as string);
      setUploadedFile(file);
    };
    reader.readAsDataURL(file);
  };

  const handleAnalyze = async (includePolyvore = true, forceMode = '') => {
    if (!uploadedFile) return;

    const modeConfig = GLOWUP_MODE_CONFIG[DEFAULT_GLOWUP_MODE];
    setIncludePolyvoreRequested(includePolyvore);
    setIsAnalyzing(true);
    const requestToken = ++requestTokenRef.current;

    try {
      const formData = new FormData();
      formData.append('image', uploadedFile);
      formData.append('top_k', String(modeConfig.topK));
      formData.append('shortlist_k', String(modeConfig.shortlistK));
      formData.append('fast_mode', modeConfig.fastMode ? '1' : '0');
      formData.append('include_polyvore', includePolyvore ? '1' : '0');
      if (forceMode) {
        formData.append('force_mode', forceMode);
      }

      const response = await fetch(apiUrl('/recommend'), {
        method: 'POST',
        headers: { ...getAuthHeader() },
        body: formData,
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401) {
          clearAuthState();
          toast({
            variant: 'destructive',
            title: 'Session Expired',
            description: 'Please log in again.',
          });
          navigate('/auth');
          return;
        }
        const message = data?.message || data?.error || 'Recommendation request failed.';
        toast({
          variant: 'destructive',
          title: 'Recommendation Failed',
          description: message,
        });
        return;
      }

      const payload = (data || {}) as Record<string, any>;
      const rows = Array.isArray(payload.results) ? payload.results : [];
      const hasWardrobe = rows.some((row) => normalizeRecommendationSource(row) === 'wardrobe');
      setShowPolyvoreRefs(!hasWardrobe);
      setRecommendResult(payload);
      setShowResults(true);
      if (rows.length > 0) {
        void fetchRecommendationExplanation(payload, requestToken);
      } else {
        setIsGeneratingExplanation(false);
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Recommendation Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setIsAnalyzing(false);
    }
  };

  const buildRecommendFacts = (payload: Record<string, any>): Record<string, unknown> | null => {
    const mode = String(payload?.mode || '');
    const row = Array.isArray(payload?.results) && payload.results.length > 0 ? payload.results[0] : null;
    if (!row || typeof row !== 'object') return null;

    const r = row as Record<string, any>;
    const d = (r?.details || {}) as Record<string, any>;
    const b = (r?.breakdown || {}) as Record<string, any>;
    return {
      mode,
      query_image: String(payload?.query_image || ''),
      candidate_image: String(r?.image_path || ''),
      candidate_item_id: String(r?.item_id || ''),
      rank: numOr(r?.rank, 1),
      label: String(d?.label || ''),
      final_score: numOr(r?.final_score, 0),
      breakdown: {
        model: numOr(b?.model, 0),
        type_prior: numOr(b?.type_prior, 0),
        color: numOr(b?.color, 0),
        brightness: numOr(b?.brightness, 0),
        pattern: numOr(b?.pattern, 0),
        cosine_shortlist_score: numOr(d?.cosine_shortlist_score, 0),
      },
      thresholds: {
        weak: numOr(d?.weak_threshold, 0.45),
        borderline: numOr(d?.borderline_threshold, 0.55),
        good: numOr(d?.good_threshold ?? d?.threshold, 0.62),
        excellent: numOr(d?.excellent_threshold, 0.72),
      },
      metadata: {
        query_category_name: String(d?.query_category_name || ''),
        candidate_category_name: String(d?.candidate_category_name || ''),
        top_category_name: String(d?.top_category || ''),
        bottom_category_name: String(d?.bottom_category || ''),
        top_primary_color: String(d?.top_primary_color || ''),
        bottom_primary_color: String(d?.bottom_primary_color || ''),
        top_pattern_name: patternType(d?.top_is_patterned, d?.top_pattern_label),
        bottom_pattern_name: patternType(d?.bottom_is_patterned, d?.bottom_pattern_label),
        top_pattern_prob: numOr(d?.top_pattern_prob, 0),
        bottom_pattern_prob: numOr(d?.bottom_pattern_prob, 0),
        query_category_source: String(d?.query_category_source || ''),
        candidate_category_source: String(d?.candidate_category_source || ''),
        query_mask_fallback: Boolean(d?.query_mask_fallback),
        candidate_mask_fallback: Boolean(d?.candidate_mask_fallback),
        query_autocrop_reason: String(d?.query_autocrop?.reason || ''),
      },
    };
  };

  const updateTopExplanationState = (
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
    setRecommendResult((prev) => {
      const base = (prev && typeof prev === 'object' ? prev : payload) as Record<string, any>;
      const rows = Array.isArray(base.results) ? [...base.results] : [];
      if (rows.length === 0 || typeof rows[0] !== 'object' || !rows[0]) {
        return base;
      }
      const first = rows[0] as Record<string, any>;
      const nextDetails: Record<string, any> = { ...(first.details || {}) };
      nextDetails.llm_status = String(llmPatch.llm_status || 'unavailable');
      nextDetails.llm_source = String(llmPatch.llm_source || '');
      nextDetails.llm_cached = Boolean(llmPatch.llm_cached || false);
      if (llmPatch.llm_explanation !== undefined) {
        nextDetails.llm_explanation = llmPatch.llm_explanation;
      }
      rows[0] = {
        ...first,
        details: nextDetails,
      };
      return {
        ...base,
        results: rows,
      };
    });
  };

  const fetchRecommendationExplanation = async (payload: Record<string, any>, requestToken: number) => {
    setIsGeneratingExplanation(true);
    try {
      const facts = buildRecommendFacts(payload);
      if (!facts) {
        updateTopExplanationState(payload, requestToken, {
          llm_status: 'unavailable',
          llm_source: 'none',
          llm_cached: false,
        });
        return;
      }
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
          clearAuthState();
          toast({
            variant: 'destructive',
            title: 'Session Expired',
            description: 'Please log in again.',
          });
          navigate('/auth');
        }
        updateTopExplanationState(payload, requestToken, {
          llm_status: 'unavailable',
          llm_source: 'none',
          llm_cached: false,
        });
        return;
      }

      updateTopExplanationState(payload, requestToken, {
        llm_status: String(llmData?.llm_status || (llmData?.llm_explanation ? 'ok' : 'unavailable')),
        llm_source: String(llmData?.llm_source || ''),
        llm_cached: Boolean(llmData?.llm_cached || false),
        llm_explanation: llmData?.llm_explanation,
      });
    } catch {
      updateTopExplanationState(payload, requestToken, {
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
    try {
      await fetch(apiUrl('/feedback'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({
          page: 'glowup',
          message: reportMessage,
        }),
      });

      toast({
        title: 'Report Submitted',
        description: 'Your report has been sent to the admin for review.',
      });
      setReportMessage('');
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Report Failed',
        description: 'Network error. Please try again.',
      });
    }
  };

  const recommendPayload =
    recommendResult && typeof recommendResult === 'object'
      ? (recommendResult as Record<string, any>)
      : null;
  const topRecommendations =
    recommendPayload && Array.isArray(recommendPayload.results)
      ? recommendPayload.results
          .filter((row) => row && typeof row === 'object')
          .slice(0, 4)
          .map((row) => row as Record<string, any>)
      : [];
  const topResult = topRecommendations[0] || null;
  const semanticDetection =
    recommendPayload?.semantic_detection && typeof recommendPayload.semantic_detection === 'object'
      ? (recommendPayload.semantic_detection as Record<string, any>)
      : null;
  const detectionStatus = String(semanticDetection?.status || '').trim().toLowerCase();
  const isAmbiguousChoice = !topResult && detectionStatus === 'ambiguous';
  const ambiguousTopConf = pct(semanticDetection?.top_crop_confidence);
  const ambiguousBottomConf = pct(semanticDetection?.bottom_crop_confidence);
  const ambiguousRecommendedMode = String(semanticDetection?.recommended_mode || '').trim().toLowerCase();
  const additionalRecommendations = topRecommendations.slice(1);
  const wardrobeMatches = additionalRecommendations.filter((row) => normalizeRecommendationSource(row) === 'wardrobe');
  const polyvoreMatches = additionalRecommendations.filter((row) => normalizeRecommendationSource(row) !== 'wardrobe');
  const topDetails = (topResult?.details || {}) as Record<string, any>;
  const topBreakdown = (topResult?.breakdown || {}) as Record<string, any>;
  const llmExplanation =
    topDetails?.llm_explanation && typeof topDetails.llm_explanation === 'object'
      ? (topDetails.llm_explanation as Record<string, any>)
      : null;
  const llmWhy = toList(llmExplanation?.why_it_works);
  const llmRisks = toList(llmExplanation?.risk_points);
  const llmSuggestion = toList(llmExplanation?.style_suggestion);
  const llmStatus = String(topDetails?.llm_status || 'deferred');
  const llmSource = String(topDetails?.llm_source || '');
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
  const finalScore = numOr(topResult?.final_score, 0);
  const topScoreLabel = String(topDetails?.label || '').trim() || scoreLabelFromThresholds(finalScore, {
    good: topDetails?.good_threshold ?? topDetails?.threshold,
    borderline: topDetails?.borderline_threshold,
    weak: topDetails?.weak_threshold,
    excellent: topDetails?.excellent_threshold,
  });
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
    { label: 'Model Fit', value: pct(topBreakdown?.model) },
    { label: 'Type Match', value: pct(topBreakdown?.type_prior) },
    { label: 'Color Harmony', value: pct(topBreakdown?.color) },
    { label: 'Brightness Balance', value: pct(topBreakdown?.brightness) },
    { label: 'Pattern Balance', value: pct(topBreakdown?.pattern) },
  ];
  const topPatternType = patternType(topDetails?.top_is_patterned, topDetails?.top_pattern_label);
  const bottomPatternType = patternType(topDetails?.bottom_is_patterned, topDetails?.bottom_pattern_label);
  const patternPairing = `${topPatternType} + ${bottomPatternType}`;
  const recommendMode = String(recommendPayload?.mode || '').trim().toLowerCase();
  const querySemantic = String(topDetails?.query_semantic || '').trim().toLowerCase();
  const queryIsTop =
    querySemantic === 'tops'
      ? true
      : querySemantic === 'bottoms'
        ? false
        : recommendMode === 'bottom2top'
          ? false
          : true;
  const queryRoleLabel = queryIsTop ? 'Top' : 'Bottom';
  const candidateRoleLabel = queryIsTop ? 'Bottom' : 'Top';
  const queryCategory = toLabel(
    topDetails?.query_category_name || (queryIsTop ? topDetails?.top_category : topDetails?.bottom_category),
  );
  const candidateCategory = toLabel(
    topDetails?.candidate_category_name || (queryIsTop ? topDetails?.bottom_category : topDetails?.top_category),
  );
  const queryColor = toLabel(queryIsTop ? topDetails?.top_primary_color : topDetails?.bottom_primary_color);
  const candidateColor = toLabel(queryIsTop ? topDetails?.bottom_primary_color : topDetails?.top_primary_color);
  const queryPatternType = patternType(
    queryIsTop ? topDetails?.top_is_patterned : topDetails?.bottom_is_patterned,
    queryIsTop ? topDetails?.top_pattern_label : topDetails?.bottom_pattern_label,
  );
  const candidatePatternType = patternType(
    queryIsTop ? topDetails?.bottom_is_patterned : topDetails?.top_is_patterned,
    queryIsTop ? topDetails?.bottom_pattern_label : topDetails?.top_pattern_label,
  );
  const queryPatternMeta = patternMeta(
    queryIsTop ? topDetails?.top_is_patterned : topDetails?.bottom_is_patterned,
    queryIsTop ? topDetails?.top_pattern_prob : topDetails?.bottom_pattern_prob,
  );
  const candidatePatternMeta = patternMeta(
    queryIsTop ? topDetails?.bottom_is_patterned : topDetails?.top_is_patterned,
    queryIsTop ? topDetails?.bottom_pattern_prob : topDetails?.top_pattern_prob,
  );
  const topResultSource = topResult ? normalizeRecommendationSource(topResult) : 'polyvore';
  const topResultSourceLabel = topResultSource === 'wardrobe' ? 'From Your Wardrobe' : 'Polyvore Fallback';
  const topResultBadgeLabel = topResultSource === 'wardrobe' ? 'Wardrobe Match' : 'Reference Only';
  const topResultName = String(
    topDetails?.wardrobe_name || topDetails?.name || topResult?.name || '',
  ).trim();
  const topResultSummary =
    topResultSource === 'wardrobe'
      ? finalScore >= 0.62
        ? 'This is the strongest wardrobe match for your uploaded piece right now.'
        : 'This keeps the result grounded in your wardrobe, but styling it carefully will matter.'
      : 'No strong wardrobe match was available, so this result is shown as an inspiration reference.';
  const topResultNextStep =
    topResultSource === 'wardrobe'
      ? 'Use this as your first choice, then compare the secondary matches if you want variety.'
      : 'Treat this as a styling direction and look for a similar item in your own closet.';
  const recommendationMessage = String(recommendPayload?.message || '').trim();
  const noWardrobeMatchMessage =
    recommendationMessage || "No matching items found in your wardrobe for this upload.";
  const loadingStage = GLOWUP_LOADING_STAGES[Math.min(loadingStageIndex, GLOWUP_LOADING_STAGES.length - 1)];
  const loadingPct = Math.round(
    ((Math.min(loadingStageIndex, GLOWUP_LOADING_STAGES.length - 1) + 1) / GLOWUP_LOADING_STAGES.length) * 100,
  );
  const loadingTip = GLOWUP_FASHION_TIPS[loadingTipIndex % GLOWUP_FASHION_TIPS.length];
  const loadingElapsed = formatElapsed(loadingElapsedMs);

  const resolveResultImageUrl = (row: Record<string, any>): string => {
    const explicit = String(row?.image_url || '').trim();
    if (explicit) return apiUrl(explicit);
    const normalized = normalizeRecommendationSource(row);
    if (normalized === 'polyvore') return '';
    const imagePath = String(row?.image_path || '').trim();
    if (!imagePath) return '';
    const fileName = imagePath.split(/[\\/]/).pop() || '';
    if (!fileName) return '';
    if (normalized === 'wardrobe') return apiUrl(`/uploads/${fileName}`);
    return apiUrl(`/catalog-images/${fileName}`);
  };
  const topResultImageSrc = topResult ? resolveResultImageUrl(topResult) : '';

  const renderMatchGrid = (rows: Record<string, any>[], sourceLabel: 'Wardrobe' | 'Polyvore') => (
    <div className="grid gap-4 md:grid-cols-3">
      {rows.map((row, idx) => {
        const imageSrc = resolveResultImageUrl(row);
        const details = (row?.details || {}) as Record<string, any>;
        const wardrobeName = String(
          details?.wardrobe_name || details?.name || row?.name || '',
        ).trim();
        const hoverTitle =
          sourceLabel === 'Wardrobe' && wardrobeName
            ? `Wardrobe: ${wardrobeName}`
            : sourceLabel === 'Wardrobe'
              ? 'Wardrobe item'
              : 'Polyvore reference';
        const rowScoreRaw = numOr(row?.final_score, 0);
        const rowScore = pct(row?.final_score);
        const rowLabel = String(details?.label || '').trim() || scoreLabelFromThresholds(rowScoreRaw, {
          good: details?.good_threshold ?? details?.threshold,
          borderline: details?.borderline_threshold,
          weak: details?.weak_threshold,
          excellent: details?.excellent_threshold,
        });
        return (
          <div key={`${sourceLabel}-${idx}`} className="overflow-hidden rounded-xl border bg-card" title={hoverTitle}>
            <div className="relative aspect-[3/4] bg-secondary/40" title={hoverTitle}>
              {imageSrc ? (
                <img
                  src={imageSrc}
                  alt={`${sourceLabel} recommendation ${idx + 1}`}
                  className="h-full w-full object-cover"
                  title={hoverTitle}
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-sm text-muted-foreground">
                  Image unavailable
                </div>
              )}
              <Badge className="absolute left-2 top-2" variant="secondary">
                {sourceLabel}
              </Badge>
            </div>
            <div className="space-y-1 p-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold">#{numOr(row?.rank, idx + 1)}</p>
                <p className="text-sm font-semibold">{rowScore}%</p>
              </div>
              <p className="text-xs text-muted-foreground">{rowLabel}</p>
              <p className="text-xs">
                {toLabel(details?.top_category)} + {toLabel(details?.bottom_category)}
              </p>
              {sourceLabel === 'Wardrobe' && wardrobeName && (
                <p className="text-[11px] text-muted-foreground">Name: {wardrobeName}</p>
              )}
              {sourceLabel === 'Polyvore' ? (
                <p className="text-[11px] text-muted-foreground">
                  Reference only. Not currently in your wardrobe.
                </p>
              ) : (
                <p className="text-[11px] text-muted-foreground">Available in your wardrobe.</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />
      {isAnalyzing && (
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
            <h1 className="text-4xl font-playfair font-bold mb-4">Glow Up</h1>
            <p className="text-muted-foreground">
              Upload a single top or bottom and get matching recommendations instantly.
            </p>
          </div>

          {!showResults ? (
            <div className="space-y-8">
              {/* Occasion Selector */}
              <></>

              {/* Upload Area */}
              <Card className="border-0 shadow-lg">
                <CardHeader>
                  <CardTitle className="font-serif text-xl">Upload Your Outfit</CardTitle>
                </CardHeader>
                <CardContent>
                  <label className="block">
                    <div className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-all ${
                      uploadedImage ? "border-primary bg-primary/5" : "border-border hover:border-primary/50 hover:bg-secondary/50"
                    }`}>
                      {uploadedImage ? (
                        <div className="space-y-4">
                          <img 
                            src={uploadedImage} 
                            alt="Uploaded outfit" 
                            className="max-h-64 mx-auto rounded-lg shadow-md"
                          />
                          <p className="text-sm text-muted-foreground">Click to change image</p>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          <div className="inline-flex p-4 rounded-full bg-secondary">
                            <Upload className="h-8 w-8 text-muted-foreground" />
                          </div>
                          <div>
                            <p className="font-medium">Drop a single item photo here</p>
                            <p className="text-sm text-muted-foreground mt-1">
                              Upload either a top or a bottom. Avoid full-body shots.
                            </p>
                            <p className="text-sm text-muted-foreground">or click to browse</p>
                          </div>
                        </div>
                      )}
                    </div>
                    <input 
                      type="file" 
                      accept="image/*" 
                      className="hidden" 
                      onChange={handleImageUpload}
                    />
                  </label>
                </CardContent>
              </Card>

              {/* Analyze Button */}
              <div className="space-y-4">
                <Button 
                  size="lg" 
                  className="w-full text-lg py-6"
                  onClick={() => void handleAnalyze(true)}
                  disabled={!uploadedImage || isAnalyzing}
                >
                  {isAnalyzing ? (
                    <>Processing...</>
                    ) : (
                      <>
                        <Sparkles className="mr-2 h-5 w-5" />
                        Get Styling Suggestions
                      </>
                    )}
                </Button>
              </div>
            </div>
          ) : (
            /* Results Section */
            <div className="space-y-8">
              {/* Action Buttons */}
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-end">
                <Button
                  variant="outline"
                  className="w-full sm:flex-1"
                  onClick={() => {
                    requestTokenRef.current += 1;
                    setShowResults(false);
                    setUploadedImage(null);
                    setUploadedFile(null);
                    setRecommendResult(null);
                    setShowPolyvoreRefs(false);
                    setIncludePolyvoreRequested(true);
                    setReportMessage('');
                    setIsGeneratingExplanation(false);
                  }}
                >
                  Try Another Outfit
                </Button>

                <Dialog>
                  <DialogTrigger asChild>
                    <Button variant="ghost" className="text-destructive hover:text-destructive hover:bg-destructive/10">
                      <AlertTriangle className="mr-2 h-4 w-4" />
                      Report Issue
                    </Button>
                  </DialogTrigger>
                  <DialogContent className="bg-card">
                    <DialogHeader>
                      <DialogTitle className="font-serif">Report an Issue</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-4 pt-4">
                      <div className="space-y-2">
                        <Label>Describe the issue</Label>
                        <Textarea
                          placeholder="Tell us what went wrong..."
                          rows={4}
                          value={reportMessage}
                          onChange={(e) => setReportMessage(e.target.value)}
                        />
                      </div>
                      <Button className="w-full" onClick={handleReport} disabled={!reportMessage.trim()}>
                        Submit Report
                      </Button>
                    </div>
                  </DialogContent>
                </Dialog>
              </div>

              {topResult ? (
                <>
              <div className="grid md:grid-cols-2 gap-8">
                {/* Analyzed Item */}
                <Card className="border-0 shadow-lg overflow-hidden">
                  <CardHeader className="bg-secondary/50">
                    <CardTitle className="font-serif text-lg">Analyzed Item</CardTitle>
                  </CardHeader>
                  <CardContent className="p-0 space-y-0">
                    <img 
                      src={uploadedImage!} 
                      alt="Analyzed clothing item"
                      className="w-full aspect-[3/4] object-cover"
                    />
                    <div className="p-4 text-sm">
                      <p className="font-semibold">{queryRoleLabel} | {queryCategory}</p>
                      <p className="text-xs text-muted-foreground mt-1">Color: {queryColor}</p>
                      <p className="text-xs text-muted-foreground">
                        Pattern: {queryPatternType} | {queryPatternMeta}
                      </p>
                    </div>
                  </CardContent>
                </Card>

                {/* Top Recommendation */}
                <Card className="border-0 shadow-lg overflow-hidden">
                  <CardHeader className="bg-primary/10">
                    <CardTitle className="font-serif text-lg flex items-center gap-2">
                      <Sparkles className="h-5 w-5 text-primary" />
                      Top Recommendation (Rank 1)
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="p-0">
                    {topResult && topResultImageSrc ? (
                      <img
                        src={topResultImageSrc}
                        alt="Top recommendation"
                        className="w-full aspect-[3/4] object-cover"
                      />
                    ) : (
                      <div className="flex aspect-[3/4] items-center justify-center bg-secondary/40 text-sm text-muted-foreground">
                        No recommendation image
                      </div>
                    )}
                    <div className="p-5 space-y-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge variant={topResultSource === 'wardrobe' ? 'default' : 'secondary'}>
                          {topResultBadgeLabel}
                        </Badge>
                        <span className="text-xs text-muted-foreground">{topResultSourceLabel}</span>
                        {topResultName && (
                          <span className="text-xs text-muted-foreground">Name: {topResultName}</span>
                        )}
                      </div>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className={`text-3xl font-semibold ${scoreTone}`}>{finalScorePct}%</p>
                          <p className="text-sm text-muted-foreground">Top recommendation score</p>
                        </div>
                        <Badge variant="secondary">{topScoreLabel}</Badge>
                      </div>
                      <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
                        <p className="font-medium">{topResultSummary}</p>
                        <p className="mt-1 text-xs text-muted-foreground">{topResultNextStep}</p>
                      </div>
                      <div className="rounded-lg border border-border bg-secondary/30 p-3 text-sm">
                        <p className="text-xs uppercase text-muted-foreground">Recommended Item</p>
                        <p className="mt-1 text-sm font-semibold">{candidateRoleLabel}</p>
                        <p className="text-sm">{candidateCategory}</p>
                        <p className="text-xs text-muted-foreground">Color: {candidateColor}</p>
                        <p className="text-xs text-muted-foreground">
                          Pattern: {candidatePatternType} | {candidatePatternMeta}
                        </p>
                      </div>
                      <p className="text-xs text-muted-foreground">Pattern pairing: {patternPairing}</p>
                      <Collapsible className="rounded-lg border border-border bg-background/80 px-3 py-2">
                        <CollapsibleTrigger className="flex w-full items-center justify-between text-sm font-medium">
                          <span>Scoring details</span>
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        </CollapsibleTrigger>
                        <CollapsibleContent className="pt-3">
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
                        </CollapsibleContent>
                      </Collapsible>
                    </div>
                  </CardContent>
                </Card>
              </div>

              <Card className="border-0 shadow-lg">
                <CardHeader className="bg-secondary/50">
                  <CardTitle className="font-serif text-lg flex items-center justify-between">
                    <span>Style Explanation (Rank 1)</span>
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
                  <CardTitle className="font-serif text-lg">More Matches (Rank 2-4)</CardTitle>
                </CardHeader>
                <CardContent className="p-5">
                  {additionalRecommendations.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No additional recommendations beyond Rank 1.
                    </p>
                  ) : (
                    <div className="space-y-6">
                      <div className="rounded-md border border-border bg-secondary/30 p-3 text-sm">
                        <p>
                          In rank 2-4: <span className="font-medium">{wardrobeMatches.length}</span> from your
                          wardrobe, <span className="font-medium">{polyvoreMatches.length}</span> from Polyvore
                          fallback.
                        </p>
                      </div>

                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-semibold">From Your Wardrobe</p>
                          <Badge variant="default">Priority</Badge>
                        </div>
                        {wardrobeMatches.length > 0 ? (
                          renderMatchGrid(wardrobeMatches, 'Wardrobe')
                        ) : (
                          <p className="text-sm text-muted-foreground">
                            No additional wardrobe match above the current threshold.
                          </p>
                        )}
                      </div>

                      {polyvoreMatches.length > 0 && (
                        <div className="space-y-3">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div>
                              <p className="text-sm font-semibold">Style References (Polyvore Dataset)</p>
                              <p className="text-xs text-muted-foreground">
                                These are fallback inspirations when your wardrobe does not fully cover the result set.
                              </p>
                            </div>
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => setShowPolyvoreRefs((prev) => !prev)}
                            >
                              {showPolyvoreRefs ? 'Hide References' : 'Show References'}
                            </Button>
                          </div>
                          {showPolyvoreRefs ? (
                            renderMatchGrid(polyvoreMatches, 'Polyvore')
                          ) : (
                            <p className="text-xs text-muted-foreground">References are collapsed by default.</p>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>
                </>
              ) : isAmbiguousChoice ? (
                <Card className="border-0 shadow-lg">
                  <CardHeader className="bg-secondary/50">
                    <CardTitle className="font-serif text-lg">Ambiguous Item Detected</CardTitle>
                  </CardHeader>
                  <CardContent className="p-5 space-y-4">
                    <p className="text-sm text-muted-foreground">
                      We detected both top and bottom signals from this image. Choose how to interpret it.
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Retry will use the default recommendation mode.
                    </p>
                    <div className="rounded-md border border-border bg-secondary/30 p-3 text-sm">
                      <p>Top confidence: <span className="font-medium">{ambiguousTopConf}%</span></p>
                      <p>Bottom confidence: <span className="font-medium">{ambiguousBottomConf}%</span></p>
                      {ambiguousRecommendedMode && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Suggested: {ambiguousRecommendedMode === 'top2bottom' ? 'Use Top' : 'Use Bottom'}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-col gap-3 sm:flex-row">
                      <Button
                        type="button"
                        className="sm:flex-1"
                        onClick={() => void handleAnalyze(includePolyvoreRequested, 'top2bottom')}
                        disabled={isAnalyzing || !uploadedFile}
                      >
                        Use Top
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        className="sm:flex-1"
                        onClick={() => void handleAnalyze(includePolyvoreRequested, 'bottom2top')}
                        disabled={isAnalyzing || !uploadedFile}
                      >
                        Use Bottom
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ) : (
                <Card className="border-0 shadow-lg">
                  <CardHeader className="bg-secondary/50">
                    <CardTitle className="font-serif text-lg">No Wardrobe Match Yet</CardTitle>
                  </CardHeader>
                  <CardContent className="p-5 space-y-4">
                    <p className="text-sm text-muted-foreground">{noWardrobeMatchMessage}</p>
                    {!includePolyvoreRequested ? (
                      <div className="space-y-2">
                        <p className="text-sm">Would you like recommendations from Polyvore references?</p>
                        <Button
                          type="button"
                          onClick={() => void handleAnalyze(true)}
                          disabled={isAnalyzing || !uploadedFile}
                        >
                          Show External Recommendations
                        </Button>
                      </div>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        External recommendations are enabled, but no result was returned for this request.
                      </p>
                    )}
                  </CardContent>
                </Card>
              )}

            </div>
          )}
        </div>
      </main>
      
      <Footer />
    </div>
  );
};

export default GlowUp;

