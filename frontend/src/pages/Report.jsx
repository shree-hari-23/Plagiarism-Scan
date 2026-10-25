import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { scansAPI } from '../api';
import { useNotification } from '../context/NotificationContext';
import {
    ArrowLeft,
    AlertTriangle,
    CheckCircle,
    Clock,
    TrendingDown,
    TrendingUp,
    Download,
    ExternalLink,
    ShieldCheck,
    Cpu,
    BookOpen,
    Globe,
    Search,
    Filter,
    Info,
    Bot,
    FileText,
    Split,
    Sliders,
    Copy,
    Check,
    Sparkles,
    Share2,
    X,
    Quote,
    Layers,
    RotateCcw
} from 'lucide-react';

function generateCitations({ title, url, author = '' }) {
    const today = new Date();
    const year = today.getFullYear();
    const months = ['Jan.', 'Feb.', 'Mar.', 'Apr.', 'May', 'Jun.', 'Jul.', 'Aug.', 'Sep.', 'Oct.', 'Nov.', 'Dec.'];
    const month = months[today.getMonth()];
    const day = today.getDate();
    const cleanTitle = title || 'Untitled Online Resource';
    const cleanUrl = url || 'https://example.com';
    let domain = 'Web Source';
    try {
        domain = new URL(cleanUrl).hostname.replace('www.', '');
    } catch {
        domain = 'Web Source';
    }

    const citeAuthor = author || domain;

    return {
        apa: `${citeAuthor}. (${year}). ${cleanTitle}. Retrieved from ${cleanUrl}`,
        mla: `"${cleanTitle}." ${domain}, ${day} ${month} ${year}, ${cleanUrl}.`,
        chicago: `${domain}. "${cleanTitle}." Accessed ${today.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })}. ${cleanUrl}.`,
        harvard: `${domain}, ${year}. ${cleanTitle}. Available at: <${cleanUrl}> [Accessed ${day} ${month} ${year}].`
    };
}

function renderDiffTokens(text, referenceText, highlightColor = 'red') {
    if (!text) return null;
    const refWords = new Set(
        (referenceText || '')
            .toLowerCase()
            .replace(/[^\w\s]/g, '')
            .split(/\s+/)
            .filter(w => w.length > 3)
    );

    const words = text.split(/(\s+)/);
    return words.map((chunk, idx) => {
        const cleanChunk = chunk.toLowerCase().replace(/[^\w]/g, '');
        const isMatched = cleanChunk.length > 3 && refWords.has(cleanChunk);
        if (isMatched) {
            return (
                <mark
                    key={idx}
                    className={`${
                        highlightColor === 'red'
                            ? 'bg-red-200 text-red-950 font-semibold'
                            : 'bg-emerald-200 text-emerald-950 font-semibold'
                    } px-0.5 rounded transition-all`}
                >
                    {chunk}
                </mark>
            );
        }
        return <span key={idx}>{chunk}</span>;
    });
}

export default function Report() {
    const { scanId } = useParams();
    const [scan, setScan] = useState(null);
    const [loading, setLoading] = useState(true);
    const [activeProofTab, setActiveProofTab] = useState('web'); // 'web' | 'ai' | 'ml'
    const [lineFilter, setLineFilter] = useState('all'); // 'all' | 'web' | 'ai' | 'ml' | 'clean'
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedLine, setSelectedLine] = useState(null);

    // Live Exclusions Toggles
    const [excludeQuotes, setExcludeQuotes] = useState(false);
    const [excludeReferences, setExcludeReferences] = useState(false);
    const [excludeMinorMatches, setExcludeMinorMatches] = useState(false);

    // Modals & Drawers State
    const [comparatorData, setComparatorData] = useState(null);
    const [citeModalData, setCiteModalData] = useState(null);
    const [copiedFormat, setCopiedFormat] = useState(null);
    const [copiedShareLink, setCopiedShareLink] = useState(false);

    const navigate = useNavigate();
    const notify = useNotification();

    useEffect(() => {
        loadScan();
    }, [scanId]);

    useEffect(() => {
        let interval;
        if (scan?.status === 'scanning' || scan?.status === 'queued') {
            interval = setInterval(loadScan, 2000);
        }
        return () => clearInterval(interval);
    }, [scan?.status]);

    const loadScan = async () => {
        try {
            const response = await scansAPI.get(scanId);
            setScan(response.data);
            setLoading(false);
        } catch (err) {
            console.error('Failed to load scan:', err);
            notify.error('Scan Load Failed', 'Could not load the requested scan report.');
            navigate('/dashboard');
        }
    };

    const cleanText = (str) => {
        if (!str || typeof str !== 'string') return '';
        return str.replace(/\\\[\d+\]|\[\d+\]|\\\[\d+|\d+\\\[\d+/g, '').replace(/\\+/g, '').trim();
    };

    const rep = scan?.report || {};
    const aiDetection = rep.ai_detection || null;
    const readability = rep.readability || null;
    const webMatches = useMemo(() => (rep.web_matches || []).map(m => ({
        ...m,
        sentence: cleanText(m.sentence),
        snippet: cleanText(m.snippet)
    })), [rep.web_matches]);

    const internalMatches = useMemo(() => (rep.matches || []).map(m => ({
        ...m,
        chunk_text: cleanText(m.chunk_text),
        best_match: m.best_match ? {
            ...m.best_match,
            text: cleanText(m.best_match.text)
        } : null
    })), [rep.matches]);

    const rawLineAnalysis = rep.line_analysis || [];

    // Helper functions for exclusions
    const isQuotation = (text) => {
        const t = text.trim();
        return (t.startsWith('"') && t.endsWith('"')) ||
               (t.startsWith('“') && t.endsWith('”')) ||
               (t.startsWith('«') && t.endsWith('»')) ||
               ((t.match(/"/g) || []).length >= 2) ||
               ((t.match(/“/g) || []).length >= 1 && (t.match(/”/g) || []).length >= 1);
    };

    const isReferenceLine = (text) => {
        const t = text.trim();
        return /^(references|bibliography|works cited|sources)\b/i.test(t) ||
               /^\[\d+\]/.test(t) ||
               /^\d+\.\s+[A-Z]/.test(t) ||
               /\b(doi:|isbn:|issn:|retrieved from|accessed on|et al\.)/i.test(t);
    };

    // Process lines with live exclusion flags
    const processedLines = useMemo(() => {
        return rawLineAnalysis.map(line => {
            const text = cleanText(line.text);
            const wordCount = text.split(/\s+/).filter(Boolean).length;
            const isQuote = isQuotation(text);
            const isRef = isReferenceLine(text);
            const isMinor = (line.category === 'web' || line.category === 'ml') && wordCount < 8;

            let isExcluded = false;
            let exclusionReason = null;
            if (excludeQuotes && isQuote) {
                isExcluded = true;
                exclusionReason = 'Direct Quote Excluded';
            } else if (excludeReferences && isRef) {
                isExcluded = true;
                exclusionReason = 'Bibliography / Reference Excluded';
            } else if (excludeMinorMatches && isMinor) {
                isExcluded = true;
                exclusionReason = 'Minor Match (< 8 words) Excluded';
            }

            return {
                ...line,
                text,
                wordCount,
                isQuote,
                isRef,
                isMinor,
                isExcluded,
                exclusionReason,
                effectiveCategory: isExcluded ? 'excluded' : line.category,
                web_proof: line.web_proof ? {
                    ...line.web_proof,
                    snippet: cleanText(line.web_proof.snippet)
                } : null,
                ml_proof: line.ml_proof ? {
                    ...line.ml_proof,
                    matched_text: cleanText(line.ml_proof.matched_text)
                } : null
            };
        });
    }, [rawLineAnalysis, excludeQuotes, excludeReferences, excludeMinorMatches]);

    // Live Dynamic Score Recalculation
    const recalculatedScore = useMemo(() => {
        if (!processedLines.length) return scan?.score ?? 0;
        const totalEvaluated = processedLines.filter(l => !l.isExcluded).length;
        if (totalEvaluated === 0) return 0;
        const matched = processedLines.filter(l => !l.isExcluded && (l.category === 'web' || l.category === 'ml')).length;
        return Math.min(100, Math.round((matched / totalEvaluated) * 100));
    }, [processedLines, scan?.score]);

    const hasActiveExclusions = excludeQuotes || excludeReferences || excludeMinorMatches;
    const excludedCount = processedLines.filter(l => l.isExcluded).length;

    // Filtered lines for display
    const filteredLines = useMemo(() => {
        return processedLines.filter(line => {
            const matchesCategory = lineFilter === 'all' ||
                (lineFilter === 'excluded' ? line.isExcluded : (!line.isExcluded && line.category === lineFilter));
            const matchesSearch = !searchQuery || line.text.toLowerCase().includes(searchQuery.toLowerCase());
            return matchesCategory && matchesSearch;
        });
    }, [processedLines, lineFilter, searchQuery]);

    const webLinesCount = processedLines.filter(l => !l.isExcluded && l.category === 'web').length;
    const aiLinesCount = processedLines.filter(l => !l.isExcluded && l.category === 'ai').length;
    const mlLinesCount = processedLines.filter(l => !l.isExcluded && l.category === 'ml').length;
    const cleanLinesCount = processedLines.filter(l => !l.isExcluded && l.category === 'clean').length;

    const handleCopyShareLink = () => {
        const verifyUrl = `${window.location.protocol}//${window.location.host}/verify/${scanId}`;
        navigator.clipboard.writeText(verifyUrl);
        setCopiedShareLink(true);
        notify.success('Link Copied', 'Public cryptographic verification link copied to clipboard!');
        setTimeout(() => setCopiedShareLink(false), 2500);
    };

    const handleCopyCitation = (text, formatKey) => {
        navigator.clipboard.writeText(text);
        setCopiedFormat(formatKey);
        notify.success('Citation Copied', `${formatKey.toUpperCase()} academic citation copied to clipboard!`);
        setTimeout(() => setCopiedFormat(null), 2000);
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 flex items-center justify-center">
                <div className="text-center">
                    <div className="w-16 h-16 rounded-2xl bg-white p-2 mx-auto mb-4 shadow-xl border border-gray-200/80 animate-pulse flex items-center justify-center">
                        <img src="/logo-icon.png" alt="Loading..." className="w-full h-full object-contain" onError={(e) => { e.target.src = '/logo.png'; }} />
                    </div>
                    <p className="text-gray-700 text-lg font-semibold">Loading forensic report...</p>
                </div>
            </div>
        );
    }

    const getScoreColor = (score) => {
        if (score < 20) return 'text-emerald-600';
        if (score < 50) return 'text-amber-600';
        return 'text-red-600';
    };

    const getScoreBg = (score) => {
        if (score < 20) return 'from-emerald-50 to-teal-50 border-emerald-200';
        if (score < 50) return 'from-amber-50 to-yellow-50 border-amber-200';
        return 'from-red-50 to-pink-50 border-red-200';
    };

    const getScoreIcon = (score) => {
        if (score < 20) return <TrendingDown className="h-12 w-12 text-emerald-600" />;
        if (score < 50) return <AlertTriangle className="h-12 w-12 text-amber-600" />;
        return <TrendingUp className="h-12 w-12 text-red-600" />;
    };

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-100 pb-16">
            {/* Sticky Header Navbar */}
            <nav className="bg-white/95 backdrop-blur-md shadow-sm border-b border-gray-200/80 sticky top-0 z-40">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                        <button
                            onClick={() => navigate('/dashboard')}
                            className="flex items-center gap-1.5 text-gray-700 hover:text-indigo-600 hover:bg-gray-100 px-3 py-1.5 rounded-lg transition-all text-xs font-bold"
                        >
                            <ArrowLeft className="h-4 w-4" />
                            <span>Dashboard</span>
                        </button>
                        <div className="h-5 w-[1px] bg-gray-200 hidden sm:block" />
                        <div className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-xl bg-white p-0.5 shadow-sm border border-gray-200/80 flex items-center justify-center overflow-hidden ring-1 ring-indigo-500/20">
                                <img
                                    src="/logo-icon.png"
                                    alt="PlagiaScan Logo"
                                    className="w-full h-full object-contain"
                                    onError={(e) => { e.target.src = '/logo.png'; }}
                                />
                            </div>
                            <span className="text-xs font-bold text-slate-800 hidden md:inline">Forensic Scan Report</span>
                        </div>
                    </div>

                    <div className="flex items-center gap-2.5 flex-wrap">
                        {/* Public Share / Verify Button */}
                        <button
                            onClick={handleCopyShareLink}
                            className="flex items-center gap-1.5 px-3.5 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-300 rounded-lg text-xs font-semibold shadow-sm transition-all"
                            title="Copy public verification link with cryptographic stamp"
                        >
                            {copiedShareLink ? (
                                <>
                                    <Check className="h-3.5 w-3.5 text-emerald-600" />
                                    <span className="text-emerald-700">Verification Link Copied!</span>
                                </>
                            ) : (
                                <>
                                    <Share2 className="h-3.5 w-3.5 text-indigo-600" />
                                    <span>Share Public Verification</span>
                                </>
                            )}
                        </button>

                        {scan.status === 'completed' && (
                            <a
                                href={`http://${window.location.hostname}:8000/api/v1/scans/${scanId}/pdf`}
                                target="_blank"
                                rel="noreferrer"
                                className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow transition-all"
                            >
                                <Download className="h-3.5 w-3.5" />
                                Export Certified PDF (with QR)
                            </a>
                        )}
                    </div>
                </div>
            </nav>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                {/* Main Card */}
                <div className="bg-white rounded-2xl shadow-xl p-6 sm:p-8 mb-6 border border-gray-200">
                    <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
                        <div className="flex items-center gap-3">
                            <div className="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center shadow-md">
                                <ShieldCheck className="h-6 w-6 text-white" />
                            </div>
                            <div>
                                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Document Integrity Audit</h1>
                                <p className="text-xs text-gray-500 mt-0.5">
                                    Scan ID: #{scan.id} • Date: {new Date(scan.created_at).toLocaleString()}
                                </p>
                            </div>
                        </div>

                        {/* Public Link Pill */}
                        <a
                            href={`/verify/${scanId}`}
                            target="_blank"
                            rel="noreferrer"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-800 border border-emerald-300 rounded-xl text-xs font-bold hover:bg-emerald-100 transition-all shadow-sm"
                        >
                            <ShieldCheck className="h-4 w-4 text-emerald-600" />
                            <span>View Public Certificate Portal</span>
                            <ExternalLink className="h-3 w-3" />
                        </a>
                    </div>

                    {/* Scanning State */}
                    {scan.status === 'scanning' || scan.status === 'queued' ? (
                        <div className="py-12 px-4 text-center">
                            <Clock className="h-14 w-14 text-indigo-600 animate-spin mx-auto mb-4" />
                            <h3 className="text-xl font-bold text-gray-800 mb-2">Scanning Document...</h3>
                            <p className="text-gray-600 text-sm max-w-lg mx-auto mb-6">
                                {scan.current_step || 'Processing chunks, verifying web sources, and evaluating AI markers...'}
                            </p>
                            <div className="w-full max-w-md mx-auto bg-gray-200 rounded-full h-3 mb-3 overflow-hidden shadow-inner">
                                <div
                                    className="bg-gradient-to-r from-indigo-500 to-purple-600 h-3 rounded-full transition-all duration-500"
                                    style={{ width: `${Math.max(scan.progress || 5, 8)}%` }}
                                ></div>
                            </div>
                            <p className="text-xs font-semibold text-indigo-600">{scan.progress || 10}% completed</p>
                        </div>
                    ) : scan.status === 'failed' ? (
                        <div className="bg-red-50 border-2 border-red-200 rounded-2xl p-8 text-center">
                            <AlertTriangle className="h-14 w-14 text-red-600 mx-auto mb-3" />
                            <h3 className="text-red-800 font-bold text-lg mb-1">Scan Failed</h3>
                            <p className="text-red-600 text-sm">{scan.report?.error || 'An unexpected error occurred during processing.'}</p>
                        </div>
                    ) : (
                        /* Completed State */
                        <>
                            {/* Live Exclusions Controls Banner */}
                            <div className="bg-gradient-to-r from-slate-50 via-indigo-50/50 to-slate-50 border border-indigo-100 rounded-2xl p-4 mb-6 shadow-sm">
                                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                    <div className="flex items-center gap-2.5">
                                        <div className="p-2 bg-indigo-600 text-white rounded-xl shadow-sm">
                                            <Sliders className="h-4 w-4" />
                                        </div>
                                        <div>
                                            <h4 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                                                <span>Live Exclusions & Real-Time Recalculator</span>
                                                {hasActiveExclusions && (
                                                    <span className="px-2 py-0.5 bg-indigo-600 text-white text-[10px] font-extrabold rounded-full animate-pulse">
                                                        ACTIVE ({excludedCount} excluded)
                                                    </span>
                                                )}
                                            </h4>
                                            <p className="text-xs text-gray-500">
                                                Turnitin-style filters. Exclude cited quotations, bibliography, or minor matches to recalculate the score in real time.
                                            </p>
                                        </div>
                                    </div>

                                    {/* Toggle Checkboxes */}
                                    <div className="flex items-center gap-2 flex-wrap">
                                        <button
                                            onClick={() => setExcludeQuotes(!excludeQuotes)}
                                            className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all flex items-center gap-1.5 ${
                                                excludeQuotes
                                                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                                                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                                            }`}
                                        >
                                            <Quote className="h-3.5 w-3.5" />
                                            <span>Quotes ("...")</span>
                                        </button>

                                        <button
                                            onClick={() => setExcludeReferences(!excludeReferences)}
                                            className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all flex items-center gap-1.5 ${
                                                excludeReferences
                                                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                                                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                                            }`}
                                        >
                                            <BookOpen className="h-3.5 w-3.5" />
                                            <span>Bibliography / References</span>
                                        </button>

                                        <button
                                            onClick={() => setExcludeMinorMatches(!excludeMinorMatches)}
                                            className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all flex items-center gap-1.5 ${
                                                excludeMinorMatches
                                                    ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm'
                                                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                                            }`}
                                        >
                                            <Filter className="h-3.5 w-3.5" />
                                            <span>Matches &lt; 8 words</span>
                                        </button>

                                        {hasActiveExclusions && (
                                            <button
                                                onClick={() => {
                                                    setExcludeQuotes(false);
                                                    setExcludeReferences(false);
                                                    setExcludeMinorMatches(false);
                                                }}
                                                className="px-2.5 py-1.5 rounded-xl text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-200 transition-all flex items-center gap-1"
                                                title="Reset all exclusions"
                                            >
                                                <RotateCcw className="h-3.5 w-3.5" />
                                                <span>Reset</span>
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Dual Scoreboard */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                                {/* Scoreboard 1: Plagiarism Score (with live recalculation badge) */}
                                <div className={`bg-gradient-to-br ${getScoreBg(hasActiveExclusions ? recalculatedScore : (scan.score ?? 0))} rounded-2xl p-6 sm:p-7 border-2 shadow-sm flex flex-col justify-between`}>
                                    <div>
                                        <div className="flex items-center justify-between gap-2 mb-3">
                                            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-white/80 border border-gray-200 text-gray-700 shadow-sm">
                                                <Globe className="h-3.5 w-3.5 text-indigo-600" />
                                                Web & Database Duplication
                                            </span>
                                            {getScoreIcon(hasActiveExclusions ? recalculatedScore : (scan.score ?? 0))}
                                        </div>

                                        <div className="flex items-center justify-between">
                                            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
                                                {hasActiveExclusions ? 'Recalculated Plagiarism Index' : 'Overall Plagiarism Score'}
                                            </p>
                                            {hasActiveExclusions && (
                                                <span className="text-xs font-bold text-gray-500 line-through">
                                                    Original: {scan.score ?? 0}%
                                                </span>
                                            )}
                                        </div>

                                        <div className="flex items-baseline gap-3 mt-1 mb-2">
                                            <p className={`text-5xl sm:text-6xl font-extrabold ${getScoreColor(hasActiveExclusions ? recalculatedScore : (scan.score ?? 0))}`}>
                                                {hasActiveExclusions ? recalculatedScore : (scan.score ?? 0)}%
                                            </p>
                                            {hasActiveExclusions && (
                                                <span className="px-2.5 py-1 bg-white/90 border border-indigo-200 text-indigo-800 text-xs font-bold rounded-lg shadow-sm">
                                                    {recalculatedScore < (scan.score ?? 0) ? `-${(scan.score ?? 0) - recalculatedScore}% excluded` : 'Recalculated'}
                                                </span>
                                            )}
                                        </div>
                                        <p className="text-sm font-medium text-gray-700 leading-snug">
                                            {(hasActiveExclusions ? recalculatedScore : (scan.score ?? 0)) < 20
                                                ? '✓ Clean — Minimal or no uncredited text duplication detected on the web or document library.'
                                                : (hasActiveExclusions ? recalculatedScore : (scan.score ?? 0)) < 50
                                                    ? '⚠ Moderate Overlap — Flagged passages match online or stored documents.'
                                                    : '⚠ Critical Duplication — Extensive uncredited content copied from external sources.'}
                                        </p>
                                    </div>

                                    {/* Granular sub-scores */}
                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-gray-300/60 text-xs">
                                        <div>
                                            <span className="text-gray-500">Verbatim:</span>
                                            <p className="text-sm font-bold text-red-600">{rep.verbatim_score ?? rep.internal_score ?? 0}%</p>
                                        </div>
                                        <div>
                                            <span className="text-gray-500">Web Overlap:</span>
                                            <p className="text-sm font-bold text-amber-600">{rep.web_score ?? 0}%</p>
                                        </div>
                                        <div>
                                            <span className="text-gray-500">Internal DB:</span>
                                            <p className="text-sm font-bold text-blue-600">{rep.internal_score ?? 0}%</p>
                                        </div>
                                        <div>
                                            <span className="text-gray-500">Web Sources:</span>
                                            <p className="text-sm font-bold text-indigo-600">{webMatches.length} online</p>
                                        </div>
                                    </div>
                                </div>

                                {/* Scoreboard 2: AI Generated Content Probability */}
                                {aiDetection ? (
                                    aiDetection.status === 'insufficient_text' || aiDetection.ai_probability === null ? (
                                        <div className="bg-gradient-to-br from-amber-50 via-orange-50 to-amber-50 rounded-2xl p-6 sm:p-7 border-2 border-amber-200 shadow-sm flex flex-col justify-between">
                                            <div>
                                                <div className="flex items-center justify-between gap-2 mb-3">
                                                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-white/80 border border-amber-200 text-amber-700 shadow-sm">
                                                        <Bot className="h-3.5 w-3.5 text-amber-600" />
                                                        AI Detection Notice
                                                    </span>
                                                    <span className="px-2.5 py-0.5 rounded-full text-xs font-bold border bg-amber-100 text-amber-800 border-amber-300">
                                                        {aiDetection.label || 'Insufficient Text'}
                                                    </span>
                                                </div>

                                                <p className="text-xs font-semibold text-amber-600 uppercase tracking-wider">Sample Size Requirement</p>
                                                <div className="flex items-baseline gap-2 mt-1 mb-2">
                                                    <p className="text-2xl sm:text-3xl font-extrabold text-amber-800">
                                                        &lt; 150 Words
                                                    </p>
                                                </div>

                                                <p className="text-sm font-medium text-amber-900 leading-snug">
                                                    {aiDetection.description || 'Document contains fewer than 150 words. Statistical stylometry requires a larger sample for dependable evaluation.'}
                                                </p>
                                            </div>

                                            <div className="mt-5 pt-4 border-t border-amber-200/80 text-xs text-amber-800/80">
                                                <span>Submitted words: <strong>{aiDetection.word_count ?? 'N/A'}</strong> &bull; Minimum required: <strong>150 words</strong></span>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="bg-gradient-to-br from-violet-50 via-purple-50 to-indigo-50 rounded-2xl p-6 sm:p-7 border-2 border-violet-200 shadow-sm flex flex-col justify-between">
                                            <div>
                                                <div className="flex items-center justify-between gap-2 mb-3">
                                                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-white/80 border border-violet-200 text-violet-700 shadow-sm">
                                                        <Bot className="h-3.5 w-3.5 text-violet-600" />
                                                        Calibrated AI Stylometrics
                                                    </span>
                                                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                                                        aiDetection.ai_probability >= 65
                                                            ? 'bg-purple-100 text-purple-800 border-purple-300'
                                                            : aiDetection.ai_probability >= 35
                                                                ? 'bg-amber-100 text-amber-800 border-amber-300'
                                                                : 'bg-emerald-100 text-emerald-800 border-emerald-300'
                                                    }`}>
                                                        {aiDetection.label}
                                                    </span>
                                                </div>

                                                <p className="text-xs font-semibold text-violet-600 uppercase tracking-wider">AI Content Probability</p>
                                                <div className="flex items-baseline gap-2 mt-1 mb-2">
                                                    <p className="text-5xl sm:text-6xl font-extrabold text-violet-700">
                                                        {aiDetection.ai_probability}%
                                                    </p>
                                                    {aiDetection.confidence && (
                                                        <span className="text-xs font-semibold px-2 py-0.5 rounded bg-violet-100 text-violet-700 border border-violet-200 uppercase">
                                                            {aiDetection.confidence} confidence
                                                        </span>
                                                    )}
                                                </div>

                                                {/* Probability Meter Bar */}
                                                <div className="w-full bg-violet-200/60 rounded-full h-2.5 mb-3 overflow-hidden">
                                                    <div
                                                        className="bg-gradient-to-r from-indigo-600 to-purple-600 h-2.5 rounded-full transition-all duration-500"
                                                        style={{ width: `${Math.min(100, Math.max(0, aiDetection.ai_probability))}%` }}
                                                    ></div>
                                                </div>

                                                <p className="text-sm font-medium text-gray-700 leading-snug">
                                                    {aiDetection.description || (
                                                        aiDetection.ai_probability >= 65
                                                            ? '🤖 Strong AI-style patterns detected: high syntactic predictability, uniform cadence, and characteristic rhetorical markers.'
                                                            : aiDetection.ai_probability >= 35
                                                                ? '⚡ Mixed signals: contains a blend of structured drafting and authentic human variation.'
                                                                : '✍ Authentic human prose: organic sentence-length variation, natural colloquialisms, and diverse vocabulary.'
                                                    )}
                                                </p>
                                            </div>

                                            {/* Granular AI Signals */}
                                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-violet-200 text-xs">
                                                <div>
                                                    <span className="text-gray-500">LLM Hallmarks:</span>
                                                    <p className="text-sm font-bold text-violet-700">
                                                        {aiDetection.details?.hallmark_hits !== undefined
                                                            ? `${aiDetection.details.hallmark_hits} hits`
                                                            : (aiDetection.details?.transition_word_score !== undefined ? `${aiDetection.details.transition_word_score}%` : '0 hits')}
                                                    </p>
                                                </div>
                                                <div>
                                                    <span className="text-gray-500">Burstiness:</span>
                                                    <p className="text-sm font-bold text-violet-700">
                                                        {aiDetection.details?.burstiness_score !== undefined
                                                            ? `${aiDetection.details.burstiness_score}%`
                                                            : (aiDetection.details?.burstiness_raw !== undefined ? `${aiDetection.details.burstiness_raw}` : 'n/a')}
                                                    </p>
                                                </div>
                                                <div>
                                                    <span className="text-gray-500">Formality:</span>
                                                    <p className="text-sm font-bold text-violet-700">
                                                        {aiDetection.details?.formality_score !== undefined
                                                            ? `${aiDetection.details.formality_score}%`
                                                            : (aiDetection.details?.informality_score !== undefined ? `${100 - aiDetection.details.informality_score}%` : 'n/a')}
                                                    </p>
                                                </div>
                                                <div>
                                                    <span className="text-gray-500">Avg Sentence:</span>
                                                    <p className="text-sm font-bold text-violet-700">
                                                        {aiDetection.details?.avg_sentence_length !== undefined
                                                            ? `${aiDetection.details.avg_sentence_length} w`
                                                            : 'n/a'}
                                                    </p>
                                                </div>
                                            </div>

                                            {/* Academic Responsibility Disclaimer */}
                                            <p className="text-[10px] text-gray-400 mt-3 italic">
                                                * Note: AI probability represents statistical stylometric similarity and must not be used as the sole determinant for academic integrity violations.
                                            </p>
                                        </div>
                                    )
                                ) : (
                                    <div className="bg-gray-50 rounded-2xl p-6 border-2 border-dashed border-gray-200 flex items-center justify-center text-gray-400 text-sm">
                                        AI evaluation completed
                                    </div>
                                )}
                            </div>

                            {/* Section: Readability & Stylometrics Scorecard */}
                            {readability && (
                                <div className="bg-white border border-gray-200 rounded-2xl p-5 mb-8 shadow-sm">
                                    <div className="flex items-center justify-between flex-wrap gap-2 mb-4">
                                        <div className="flex items-center gap-2">
                                            <div className="p-2 bg-indigo-100 rounded-lg text-indigo-700">
                                                <BookOpen className="h-5 w-5" />
                                            </div>
                                            <div>
                                                <h3 className="text-base font-bold text-gray-900">Readability & Stylometrics Matrix</h3>
                                                <p className="text-xs text-gray-500">Linguistic complexity, lexical diversity, and syntactic voice profiling.</p>
                                            </div>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 text-center">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase">Flesch Reading Ease</p>
                                            <p className="text-2xl font-black text-indigo-600 mt-1">{readability.flesch_reading_ease}</p>
                                            <span className="inline-block mt-1 px-2 py-0.5 bg-indigo-50 border border-indigo-200 text-indigo-700 rounded text-[10px] font-bold">
                                                {readability.reading_ease_level}
                                            </span>
                                        </div>

                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 text-center">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase">Grade Level (FKGL)</p>
                                            <p className="text-2xl font-black text-slate-800 mt-1">Grade {readability.flesch_kincaid_grade}</p>
                                            <p className="text-[10px] text-gray-500 mt-1">Flesch-Kincaid Scale</p>
                                        </div>

                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 text-center">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase">Gunning Fog Index</p>
                                            <p className="text-2xl font-black text-slate-800 mt-1">{readability.gunning_fog_index}</p>
                                            <span className="inline-block mt-1 px-2 py-0.5 bg-slate-100 text-gray-600 rounded text-[10px] font-semibold">
                                                {readability.fog_reading_level}
                                            </span>
                                        </div>

                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 text-center">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase">Lexical Diversity (TTR)</p>
                                            <p className="text-2xl font-black text-purple-600 mt-1">{readability.lexical_diversity_ttr}%</p>
                                            <p className="text-[10px] text-gray-500 mt-1">Unique vocabulary ratio</p>
                                        </div>

                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 text-center">
                                            <p className="text-[11px] font-bold text-gray-500 uppercase">Passive Voice Ratio</p>
                                            <p className="text-2xl font-black text-amber-600 mt-1">{readability.passive_voice_ratio}%</p>
                                            <p className="text-[10px] text-gray-500 mt-1">{readability.passive_sentences_count} passive sentences</p>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {/* Section: Interactive Document Highlighter */}
                            <div className="mb-10">
                                <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
                                    <div className="flex items-center gap-2">
                                        <div className="p-2 bg-indigo-100 rounded-lg text-indigo-700">
                                            <FileText className="h-5 w-5" />
                                        </div>
                                        <div>
                                            <h2 className="text-lg font-bold text-gray-900">Interactive Document Highlighter</h2>
                                            <p className="text-xs text-gray-500">Click any flagged sentence to inspect external sources, compare side-by-side, or generate citations.</p>
                                        </div>
                                    </div>

                                    {/* Category Filter Pills */}
                                    <div className="flex items-center gap-1.5 flex-wrap text-xs font-semibold">
                                        <button
                                            onClick={() => setLineFilter('all')}
                                            className={`px-3 py-1.5 rounded-lg border transition-all ${
                                                lineFilter === 'all'
                                                    ? 'bg-gray-800 text-white border-gray-800 shadow-sm'
                                                    : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'
                                            }`}
                                        >
                                            All Lines ({processedLines.length})
                                        </button>
                                        <button
                                            onClick={() => setLineFilter('web')}
                                            className={`px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                                                lineFilter === 'web'
                                                    ? 'bg-red-600 text-white border-red-600 shadow-sm'
                                                    : 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100'
                                            }`}
                                        >
                                            <span className="w-2 h-2 rounded-full bg-red-500"></span>
                                            Web Plagiarism ({webLinesCount})
                                        </button>
                                        <button
                                            onClick={() => setLineFilter('ai')}
                                            className={`px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                                                lineFilter === 'ai'
                                                    ? 'bg-purple-600 text-white border-purple-600 shadow-sm'
                                                    : 'bg-purple-50 text-purple-700 border-purple-200 hover:bg-purple-100'
                                            }`}
                                        >
                                            <span className="w-2 h-2 rounded-full bg-purple-500"></span>
                                            AI Generated ({aiLinesCount})
                                        </button>
                                        <button
                                            onClick={() => setLineFilter('ml')}
                                            className={`px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                                                lineFilter === 'ml'
                                                    ? 'bg-blue-600 text-white border-blue-600 shadow-sm'
                                                    : 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100'
                                            }`}
                                        >
                                            <span className="w-2 h-2 rounded-full bg-blue-500"></span>
                                            ML Vector Match ({mlLinesCount})
                                        </button>
                                        <button
                                            onClick={() => setLineFilter('clean')}
                                            className={`px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                                                lineFilter === 'clean'
                                                    ? 'bg-emerald-600 text-white border-emerald-600 shadow-sm'
                                                    : 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                                            }`}
                                        >
                                            <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
                                            Original Human ({cleanLinesCount})
                                        </button>
                                        {excludedCount > 0 && (
                                            <button
                                                onClick={() => setLineFilter('excluded')}
                                                className={`px-3 py-1.5 rounded-lg border transition-all flex items-center gap-1.5 ${
                                                    lineFilter === 'excluded'
                                                        ? 'bg-slate-700 text-white border-slate-700 shadow-sm'
                                                        : 'bg-slate-100 text-slate-700 border-slate-300 hover:bg-slate-200'
                                                }`}
                                            >
                                                <span className="w-2 h-2 rounded-full bg-slate-400"></span>
                                                Excluded ({excludedCount})
                                            </button>
                                        )}
                                    </div>
                                </div>

                                {/* Live Search Bar */}
                                <div className="mb-4 relative">
                                    <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                                    <input
                                        type="text"
                                        placeholder="Search within document sentences..."
                                        value={searchQuery}
                                        onChange={(e) => setSearchQuery(e.target.value)}
                                        className="w-full pl-10 pr-4 py-2 bg-slate-50 border border-gray-200 rounded-xl text-xs sm:text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all"
                                    />
                                    {searchQuery && (
                                        <button
                                            onClick={() => setSearchQuery('')}
                                            className="absolute right-3.5 top-1/2 -translate-y-1/2 text-xs text-gray-400 hover:text-gray-600"
                                        >
                                            Clear
                                        </button>
                                    )}
                                </div>

                                {/* Main Highlighter Layout: Document Sentences + Side Inspector */}
                                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                                    {/* Document Sentences Container */}
                                    <div className="lg:col-span-7 bg-slate-50/70 border border-gray-200 rounded-2xl p-5 max-h-[550px] overflow-y-auto space-y-2 font-sans shadow-inner">
                                        {filteredLines.length === 0 ? (
                                            <div className="py-12 text-center text-gray-500 text-sm">
                                                No lines matching the current filter criteria.
                                            </div>
                                        ) : (
                                            filteredLines.map((line) => {
                                                const isSelected = selectedLine?.line_index === line.line_index;

                                                let styleClasses = 'bg-white border-gray-200 hover:border-gray-300 text-gray-800';
                                                let badge = null;

                                                if (line.isExcluded) {
                                                    styleClasses = isSelected
                                                        ? 'bg-slate-200 border-slate-400 ring-2 ring-slate-400 text-slate-600'
                                                        : 'bg-slate-100/80 border-slate-200 text-slate-500 opacity-75';
                                                    badge = (
                                                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-200 text-slate-700 text-[10px] font-bold uppercase tracking-wider">
                                                            {line.exclusionReason}
                                                        </span>
                                                    );
                                                } else if (line.category === 'web') {
                                                    styleClasses = isSelected
                                                        ? 'bg-red-100/90 border-red-500 shadow-sm text-red-950 font-medium ring-2 ring-red-400'
                                                        : 'bg-red-50/70 border-red-200 hover:bg-red-100/80 text-red-900';
                                                    badge = (
                                                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-red-200/80 text-red-800 text-[10px] font-bold uppercase tracking-wider">
                                                            <Globe className="h-2.5 w-2.5" /> Web Match
                                                        </span>
                                                    );
                                                } else if (line.category === 'ai') {
                                                    styleClasses = isSelected
                                                        ? 'bg-purple-100/90 border-purple-500 shadow-sm text-purple-950 font-medium ring-2 ring-purple-400'
                                                        : 'bg-purple-50/70 border-purple-200 hover:bg-purple-100/80 text-purple-900';
                                                    badge = (
                                                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-purple-200/80 text-purple-800 text-[10px] font-bold uppercase tracking-wider">
                                                            <Bot className="h-2.5 w-2.5" /> AI: {line.confidence}%
                                                        </span>
                                                    );
                                                } else if (line.category === 'ml') {
                                                    styleClasses = isSelected
                                                        ? 'bg-blue-100/90 border-blue-500 shadow-sm text-blue-950 font-medium ring-2 ring-blue-400'
                                                        : 'bg-blue-50/70 border-blue-200 hover:bg-blue-100/80 text-blue-900';
                                                    badge = (
                                                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-blue-200/80 text-blue-800 text-[10px] font-bold uppercase tracking-wider">
                                                            <Cpu className="h-2.5 w-2.5" /> ML Vector
                                                        </span>
                                                    );
                                                } else {
                                                    styleClasses = isSelected
                                                        ? 'bg-emerald-50 border-emerald-400 ring-2 ring-emerald-300'
                                                        : 'bg-white border-gray-200 hover:bg-gray-50';
                                                    badge = (
                                                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-gray-100 text-gray-500 text-[10px] font-semibold">
                                                            Clean
                                                        </span>
                                                    );
                                                }

                                                return (
                                                    <div
                                                        key={line.line_index}
                                                        onClick={() => setSelectedLine(line)}
                                                        className={`p-3 rounded-xl border transition-all cursor-pointer text-xs sm:text-sm leading-relaxed ${styleClasses}`}
                                                    >
                                                        <div className="flex items-center justify-between gap-2 mb-1 text-[11px] text-gray-400">
                                                            <span className="font-mono font-semibold">#{line.line_index}</span>
                                                            {badge}
                                                        </div>
                                                        <p className={line.isExcluded ? 'line-through opacity-80' : ''}>{line.text}</p>
                                                    </div>
                                                );
                                            })
                                        )}
                                    </div>

                                    {/* Forensic Inspector Pane */}
                                    <div className="lg:col-span-5 bg-white border border-gray-200 rounded-2xl p-5 shadow-sm flex flex-col justify-between">
                                        {selectedLine ? (
                                            <div>
                                                <div className="flex items-center justify-between gap-2 pb-3 mb-4 border-b border-gray-100">
                                                    <div className="flex items-center gap-2">
                                                        <span className="text-xs font-bold font-mono px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded-md">
                                                            Line #{selectedLine.line_index}
                                                        </span>
                                                        <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${
                                                            selectedLine.isExcluded
                                                                ? 'bg-slate-200 text-slate-800'
                                                                : selectedLine.category === 'web'
                                                                    ? 'bg-red-100 text-red-800'
                                                                    : selectedLine.category === 'ai'
                                                                        ? 'bg-purple-100 text-purple-800'
                                                                        : selectedLine.category === 'ml'
                                                                            ? 'bg-blue-100 text-blue-800'
                                                                            : 'bg-emerald-100 text-emerald-800'
                                                        }`}>
                                                            {selectedLine.isExcluded ? 'EXCLUDED FROM SCORE' : `${selectedLine.category.toUpperCase()} CLASSIFICATION`}
                                                        </span>
                                                    </div>
                                                    <button
                                                        onClick={() => setSelectedLine(null)}
                                                        className="text-xs text-gray-400 hover:text-gray-600"
                                                    >
                                                        Close
                                                    </button>
                                                </div>

                                                <div className="mb-4">
                                                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Inspected Sentence Text</p>
                                                    <p className="text-xs sm:text-sm text-gray-900 bg-slate-50 p-3 rounded-xl border border-gray-200 italic leading-relaxed">
                                                        "{selectedLine.text}"
                                                    </p>
                                                </div>

                                                <div className="mb-4">
                                                    <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-1">Forensic Diagnosis</p>
                                                    <p className="text-xs sm:text-sm text-gray-700 leading-snug">
                                                        {selectedLine.reason}
                                                    </p>
                                                </div>

                                                {/* Category Specific Proof details */}
                                                {(selectedLine.category === 'web' || selectedLine.web_proof) && selectedLine.web_proof && (() => {
                                                    const isPossibleSource = selectedLine.web_proof.verification_status === 'POSSIBLE_RELATED_SOURCE' || selectedLine.web_proof.match_type === 'semantic';
                                                    return (
                                                        <div className="space-y-3 pt-2">
                                                            <div className={`border rounded-xl p-3.5 ${isPossibleSource ? 'bg-amber-50 border-amber-200' : 'bg-red-50 border-red-200'}`}>
                                                                <div className="flex items-center justify-between gap-2 mb-2 flex-wrap">
                                                                    <span className={`text-xs font-bold flex items-center gap-1.5 ${isPossibleSource ? 'text-amber-900' : 'text-red-900'}`}>
                                                                        <Globe className={`h-3.5 w-3.5 ${isPossibleSource ? 'text-amber-600' : 'text-red-600'}`} />
                                                                        {isPossibleSource ? 'POSSIBLE SOURCE' : 'WEB MATCH'}
                                                                    </span>
                                                                    <div className="flex items-center gap-1.5 flex-wrap">
                                                                        {selectedLine.web_proof.matched_words > 0 && !isPossibleSource && (
                                                                            <span className="text-[11px] font-semibold text-gray-700 bg-white border border-gray-200 px-2 py-0.5 rounded">
                                                                                Continuous: {selectedLine.web_proof.matched_words} words
                                                                            </span>
                                                                        )}
                                                                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded ${isPossibleSource ? 'text-amber-800 bg-amber-100' : 'text-red-700 bg-red-100'}`}>
                                                                            {isPossibleSource ? 'Semantic similarity' : (selectedLine.web_proof.match_type === 'exact' ? 'Exact N-gram' : (selectedLine.web_proof.match_type || 'Exact N-gram'))}
                                                                        </span>
                                                                        {!isPossibleSource && selectedLine.web_proof.confidence && (
                                                                            <span className="text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                                                                                {selectedLine.web_proof.confidence}
                                                                            </span>
                                                                        )}
                                                                    </div>
                                                                </div>

                                                                <p className="text-xs font-bold text-gray-900 mb-1">{selectedLine.web_proof.source_title}</p>
                                                                <p className={`text-xs line-clamp-3 italic mb-3 bg-white p-2 rounded border ${isPossibleSource ? 'text-amber-900 border-amber-100' : 'text-gray-600 border-red-100'}`}>
                                                                    "{selectedLine.web_proof.snippet}"
                                                                </p>

                                                                {isPossibleSource && (
                                                                    <div className="mb-3 text-[11px] text-amber-800 bg-amber-100/70 p-2 rounded border border-amber-200 flex flex-col gap-0.5">
                                                                        <span className="font-bold">Exact Textual Overlap: Insufficient</span>
                                                                        <span>This page may discuss similar information, but direct copying was not verified.</span>
                                                                    </div>
                                                                )}
                                                                {!isPossibleSource && (
                                                                    <p className="text-[11px] text-emerald-700 font-medium mb-3 flex items-center gap-1">
                                                                        <CheckCircle className="h-3 w-3 inline" /> Direct textual overlap verified.
                                                                    </p>
                                                                )}

                                                                {/* Action Buttons: Open Link, Side-by-Side Comparator, Fix & Cite */}
                                                                <div className="flex flex-wrap items-center gap-2">
                                                                    {selectedLine.web_proof.source_url && (
                                                                        <a
                                                                            href={selectedLine.web_proof.source_url}
                                                                            target="_blank"
                                                                            rel="noreferrer"
                                                                            className={`inline-flex items-center gap-1.5 text-xs font-bold text-white px-3 py-1.5 rounded-lg shadow-sm transition-all ${isPossibleSource ? 'bg-amber-600 hover:bg-amber-700' : 'bg-red-600 hover:bg-red-700'}`}
                                                                        >
                                                                            <span>Open Web Link</span>
                                                                            <ExternalLink className="h-3.5 w-3.5" />
                                                                        </a>
                                                                    )}

                                                                    {/* Side-by-Side Comparator Button */}
                                                                    <button
                                                                        onClick={() => setComparatorData({
                                                                            suspectText: selectedLine.text,
                                                                            sourceText: selectedLine.web_proof.snippet,
                                                                            sourceTitle: selectedLine.web_proof.source_title,
                                                                            sourceUrl: selectedLine.web_proof.source_url,
                                                                            matchType: isPossibleSource ? 'Semantic Similarity' : (selectedLine.web_proof.match_type || 'Verbatim Match')
                                                                        })}
                                                                        className="inline-flex items-center gap-1.5 text-xs font-bold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 px-3 py-1.5 rounded-lg shadow-sm transition-all"
                                                                    >
                                                                        <Split className="h-3.5 w-3.5" />
                                                                        <span>Compare Side-by-Side</span>
                                                                    </button>

                                                                    {/* 1-Click Fix & Cite Button */}
                                                                    <button
                                                                        onClick={() => setCiteModalData({
                                                                            sentence: selectedLine.text,
                                                                            title: selectedLine.web_proof.source_title,
                                                                            url: selectedLine.web_proof.source_url
                                                                        })}
                                                                        className="inline-flex items-center gap-1.5 text-xs font-bold text-purple-700 bg-purple-50 hover:bg-purple-100 border border-purple-200 px-3 py-1.5 rounded-lg shadow-sm transition-all"
                                                                    >
                                                                        <Sparkles className="h-3.5 w-3.5" />
                                                                        <span>Fix &amp; Cite</span>
                                                                    </button>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    );
                                                })()}

                                                {selectedLine.category === 'ai' && (
                                                    <div className="space-y-3 pt-2">
                                                        <div className="bg-purple-50 border border-purple-200 rounded-xl p-3.5">
                                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                                <span className="text-xs font-bold text-purple-900 flex items-center gap-1.5">
                                                                    <Bot className="h-3.5 w-3.5 text-purple-600" />
                                                                    Synthetic Pattern Caught
                                                                </span>
                                                                <span className="text-xs font-extrabold text-purple-700">
                                                                    {selectedLine.confidence}% Confidence
                                                                </span>
                                                            </div>
                                                            {selectedLine.hallmarks && selectedLine.hallmarks.length > 0 && (
                                                                <div className="mt-2">
                                                                    <p className="text-[11px] font-semibold text-purple-800 uppercase mb-1">Detected LLM Rhetorical Markers:</p>
                                                                    <div className="flex flex-wrap gap-1.5">
                                                                        {selectedLine.hallmarks.map((h, i) => (
                                                                            <span key={i} className="px-2 py-0.5 bg-white border border-purple-300 rounded text-xs font-bold text-purple-900">
                                                                                "{h}"
                                                                            </span>
                                                                        ))}
                                                                    </div>
                                                                </div>
                                                            )}
                                                        </div>
                                                    </div>
                                                )}

                                                {selectedLine.category === 'ml' && selectedLine.ml_proof && (
                                                    <div className="space-y-3 pt-2">
                                                        <div className="bg-blue-50 border border-blue-200 rounded-xl p-3.5">
                                                            <div className="flex items-center justify-between gap-2 mb-2">
                                                                <span className="text-xs font-bold text-blue-900 flex items-center gap-1.5">
                                                                    <Cpu className="h-3.5 w-3.5 text-blue-600" />
                                                                    Internal Vector Match
                                                                </span>
                                                                <span className="text-xs font-bold text-blue-700">
                                                                    {selectedLine.ml_proof.similarity}% Similarity
                                                                </span>
                                                            </div>
                                                            <p className="text-xs font-bold text-gray-900 mb-1">Internal Document: #{selectedLine.ml_proof.source_doc_id}</p>
                                                            <p className="text-xs text-gray-600 italic bg-white p-2 rounded border border-blue-100 mb-3">
                                                                "{selectedLine.ml_proof.matched_text}"
                                                            </p>

                                                            <button
                                                                onClick={() => setComparatorData({
                                                                    suspectText: selectedLine.text,
                                                                    sourceText: selectedLine.ml_proof.matched_text,
                                                                    sourceTitle: `Internal Institutional Document #${selectedLine.ml_proof.source_doc_id}`,
                                                                    sourceUrl: null,
                                                                    matchType: `${selectedLine.ml_proof.similarity}% Vector Match`
                                                                })}
                                                                className="inline-flex items-center gap-1.5 text-xs font-bold text-blue-700 bg-blue-100 hover:bg-blue-200 px-3 py-1.5 rounded-lg shadow-sm transition-all"
                                                            >
                                                                <Split className="h-3.5 w-3.5" />
                                                                <span>Compare Side-by-Side</span>
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        ) : (
                                            <div className="py-16 text-center text-gray-400 my-auto">
                                                <Info className="h-10 w-10 mx-auto mb-2 text-gray-300" />
                                                <p className="text-xs font-bold text-gray-600 uppercase tracking-wider">No Line Selected</p>
                                                <p className="text-xs text-gray-400 mt-1 max-w-xs mx-auto">
                                                    Select any sentence from the document highlighter to view its external web source link, side-by-side diff, LLM hallmarks, or ML vector proof.
                                                </p>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Section: 3-Pillar Proof Breakdown Tabs */}
                            <div className="mt-8 border-t border-gray-200 pt-8">
                                <div className="flex items-center justify-between flex-wrap gap-4 mb-6">
                                    <div>
                                        <h2 className="text-xl font-bold text-gray-900">3-Pillar Forensic Proof Breakdown</h2>
                                        <p className="text-xs text-gray-500 mt-0.5">Comprehensive audit trail across Web Duplication, AI Heuristics, and ML Semantic Vector Match.</p>
                                    </div>

                                    {/* Proof Category Navigation */}
                                    <div className="flex border border-gray-200 rounded-xl p-1 bg-slate-50 text-xs font-bold">
                                        <button
                                            onClick={() => setActiveProofTab('web')}
                                            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                                                activeProofTab === 'web'
                                                    ? 'bg-white text-indigo-700 shadow-sm'
                                                    : 'text-gray-600 hover:text-gray-900'
                                            }`}
                                        >
                                            <Globe className="h-3.5 w-3.5" />
                                            <span>Web Content Proof ({webMatches.length})</span>
                                        </button>
                                        <button
                                            onClick={() => setActiveProofTab('ai')}
                                            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                                                activeProofTab === 'ai'
                                                    ? 'bg-white text-purple-700 shadow-sm'
                                                    : 'text-gray-600 hover:text-gray-900'
                                            }`}
                                        >
                                            <Bot className="h-3.5 w-3.5" />
                                            <span>AI Content Proof ({aiDetection ? `${aiDetection.ai_probability}%` : 'N/A'})</span>
                                        </button>
                                        <button
                                            onClick={() => setActiveProofTab('ml')}
                                            className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-all ${
                                                activeProofTab === 'ml'
                                                    ? 'bg-white text-blue-700 shadow-sm'
                                                    : 'text-gray-600 hover:text-gray-900'
                                            }`}
                                        >
                                            <Cpu className="h-3.5 w-3.5" />
                                            <span>ML &amp; Semantic Proof ({internalMatches.length})</span>
                                        </button>
                                    </div>
                                </div>

                                {/* Tab 1: Web Content Proof */}
                                {activeProofTab === 'web' && (
                                    <div className="space-y-4">
                                        {webMatches.length === 0 ? (
                                            <div className="p-8 text-center bg-emerald-50/60 rounded-2xl border border-emerald-200">
                                                <CheckCircle className="h-10 w-10 text-emerald-500 mx-auto mb-2" />
                                                <p className="text-emerald-900 font-bold text-sm">No Uncredited Web Duplication Found</p>
                                                <p className="text-emerald-600 text-xs mt-1">Multi-engine search verified that document passages do not match public online encyclopedias or published articles.</p>
                                            </div>
                                        ) : (
                                            webMatches.map((wm, idx) => (
                                                <div key={idx} className="bg-slate-50 border border-gray-200 rounded-xl p-5 hover:border-indigo-300 transition-all shadow-sm">
                                                    <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                                                        <div className="flex items-center gap-2">
                                                            <span className="w-6 h-6 rounded-full bg-red-100 text-red-700 font-bold text-xs flex items-center justify-center">
                                                                {idx + 1}
                                                            </span>
                                                            <p className="text-sm font-bold text-gray-900">{wm.source_title || 'Online Article'}</p>
                                                        </div>
                                                        <div className="flex items-center gap-2">
                                                            <button
                                                                onClick={() => setComparatorData({
                                                                    suspectText: wm.sentence,
                                                                    sourceText: wm.snippet,
                                                                    sourceTitle: wm.source_title,
                                                                    sourceUrl: wm.source_url,
                                                                    matchType: wm.match_type || 'Web Match'
                                                                })}
                                                                className="flex items-center gap-1.5 px-3 py-1 bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 text-indigo-700 rounded-lg text-xs font-bold shadow-sm transition-all"
                                                            >
                                                                <Split className="h-3.5 w-3.5" />
                                                                <span>Side-by-Side Diff</span>
                                                            </button>

                                                            <button
                                                                onClick={() => setCiteModalData({
                                                                    sentence: wm.sentence,
                                                                    title: wm.source_title,
                                                                    url: wm.source_url
                                                                })}
                                                                className="flex items-center gap-1.5 px-3 py-1 bg-purple-50 border border-purple-200 hover:bg-purple-100 text-purple-700 rounded-lg text-xs font-bold shadow-sm transition-all"
                                                            >
                                                                <Sparkles className="h-3.5 w-3.5" />
                                                                <span>Cite Source</span>
                                                            </button>

                                                            {wm.source_url && (
                                                                <a
                                                                    href={wm.source_url}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    className="flex items-center gap-1.5 px-3 py-1 bg-white border border-gray-300 hover:border-gray-400 text-gray-700 hover:text-gray-900 rounded-lg text-xs font-bold shadow-sm transition-all"
                                                                >
                                                                    <span>Visit Link</span>
                                                                    <ExternalLink className="h-3.5 w-3.5" />
                                                                </a>
                                                            )}
                                                        </div>
                                                    </div>

                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                                                        <div className="bg-white p-3.5 rounded-lg border border-red-200 border-l-4 border-l-red-500">
                                                            <p className="font-bold text-red-800 uppercase tracking-wider text-[10px] mb-1">Suspect Document Excerpt:</p>
                                                            <p className="text-gray-800 italic leading-relaxed">"{wm.sentence}"</p>
                                                        </div>
                                                        <div className="bg-white p-3.5 rounded-lg border border-gray-200 border-l-4 border-l-indigo-500">
                                                            <p className="font-bold text-indigo-800 uppercase tracking-wider text-[10px] mb-1">Matched Web Source Prose:</p>
                                                            <p className="text-gray-800 leading-relaxed">"{wm.snippet}"</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}

                                {/* Tab 2: AI Content Proof */}
                                {activeProofTab === 'ai' && (
                                    <div className="space-y-6">
                                        {aiDetection ? (
                                            <>
                                                <div className="bg-gradient-to-br from-violet-50 via-purple-50 to-indigo-50 border border-purple-200 rounded-2xl p-6">
                                                    <h3 className="text-base font-bold text-purple-900 mb-2">5-Signal NLP Forensic Analysis Matrix</h3>
                                                    <p className="text-xs text-gray-600 mb-6 max-w-2xl">
                                                        Evaluates syntactic variance, lexical predictability, and robotic rhetorical patterns characteristic of Large Language Models.
                                                    </p>

                                                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                                                        <div className="bg-white p-4 rounded-xl border border-purple-100 shadow-sm">
                                                            <p className="text-xs font-bold text-gray-500 uppercase">1. Burstiness Score</p>
                                                            <p className="text-2xl font-black text-purple-700 mt-1">{aiDetection.details?.burstiness_score ?? 0}%</p>
                                                            <p className="text-[11px] text-gray-500 mt-1">Sentence length variability standard deviation</p>
                                                        </div>

                                                        <div className="bg-white p-4 rounded-xl border border-purple-100 shadow-sm">
                                                            <p className="text-xs font-bold text-gray-500 uppercase">2. Lexical Richness (TTR)</p>
                                                            <p className="text-2xl font-black text-purple-700 mt-1">{aiDetection.details?.vocabulary_richness_score ?? 0}%</p>
                                                            <p className="text-[11px] text-gray-500 mt-1">Type-token ratio across unique vocabulary</p>
                                                        </div>

                                                        <div className="bg-white p-4 rounded-xl border border-purple-100 shadow-sm">
                                                            <p className="text-xs font-bold text-gray-500 uppercase">3. Transition Overuse</p>
                                                            <p className="text-2xl font-black text-purple-700 mt-1">{aiDetection.details?.transition_word_score ?? 0}%</p>
                                                            <p className="text-[11px] text-gray-500 mt-1">Density of formulaic discourse connectives</p>
                                                        </div>

                                                        <div className="bg-white p-4 rounded-xl border border-purple-100 shadow-sm">
                                                            <p className="text-xs font-bold text-gray-500 uppercase">4. Sentence Cadence</p>
                                                            <p className="text-2xl font-black text-purple-700 mt-1">{aiDetection.details?.sentence_length_score ?? 0}%</p>
                                                            <p className="text-[11px] text-gray-500 mt-1">Mean {aiDetection.details?.avg_sentence_length ?? 0} words per sentence</p>
                                                        </div>

                                                        <div className="bg-white p-4 rounded-xl border border-purple-100 shadow-sm">
                                                            <p className="text-xs font-bold text-gray-500 uppercase">5. Formality &amp; Contractions</p>
                                                            <p className="text-2xl font-black text-purple-700 mt-1">{aiDetection.details?.informality_score ?? 0}%</p>
                                                            <p className="text-[11px] text-gray-500 mt-1">Absence of natural colloquial phrasing</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            </>
                                        ) : (
                                            <div className="p-8 text-center text-gray-500 text-sm">
                                                No AI detection data recorded for this scan.
                                            </div>
                                        )}
                                    </div>
                                )}

                                {/* Tab 3: ML & Semantic Vector Proof */}
                                {activeProofTab === 'ml' && (
                                    <div className="space-y-4">
                                        {internalMatches.length === 0 ? (
                                            <div className="p-8 text-center bg-blue-50/60 rounded-2xl border border-blue-200">
                                                <CheckCircle className="h-10 w-10 text-blue-500 mx-auto mb-2" />
                                                <p className="text-blue-900 font-bold text-sm">No Internal Institutional Duplication</p>
                                                <p className="text-blue-600 text-xs mt-1">Vector embeddings confirmed no high cosine similarity matches against other student submissions or archived library documents.</p>
                                            </div>
                                        ) : (
                                            internalMatches.map((im, idx) => (
                                                <div key={idx} className="bg-slate-50 border border-gray-200 rounded-xl p-5 shadow-sm">
                                                    <div className="flex items-center justify-between gap-2 mb-3">
                                                        <span className="text-sm font-bold text-gray-900">
                                                            Internal Document Archive #{im.best_match?.source_doc_id || 'Library Doc'}
                                                        </span>
                                                        <div className="flex items-center gap-2">
                                                            <button
                                                                onClick={() => setComparatorData({
                                                                    suspectText: im.chunk_text,
                                                                    sourceText: im.best_match?.text,
                                                                    sourceTitle: `Archive Document #${im.best_match?.source_doc_id}`,
                                                                    sourceUrl: null,
                                                                    matchType: `${Math.round((im.best_match?.score || 0) * 100)}% Cosine Similarity`
                                                                })}
                                                                className="px-2.5 py-1 bg-blue-50 text-blue-700 border border-blue-200 rounded-lg text-xs font-bold hover:bg-blue-100 transition-all flex items-center gap-1"
                                                            >
                                                                <Split className="h-3 w-3" />
                                                                <span>Side-by-Side</span>
                                                            </button>
                                                            <span className="text-xs font-bold text-blue-700 bg-blue-100 px-2.5 py-0.5 rounded-full">
                                                                {Math.round((im.best_match?.score || 0) * 100)}% Similarity
                                                            </span>
                                                        </div>
                                                    </div>
                                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
                                                        <div className="bg-white p-3 rounded-lg border border-gray-200">
                                                            <p className="font-bold text-gray-700 text-[10px] uppercase mb-1">Suspect Text:</p>
                                                            <p className="text-gray-800 italic">"{im.chunk_text}"</p>
                                                        </div>
                                                        <div className="bg-white p-3 rounded-lg border border-blue-200">
                                                            <p className="font-bold text-blue-800 text-[10px] uppercase mb-1">Archived Repository Content:</p>
                                                            <p className="text-gray-800">"{im.best_match?.text}"</p>
                                                        </div>
                                                    </div>
                                                </div>
                                            ))
                                        )}
                                    </div>
                                )}
                            </div>
                        </>
                    )}
                </div>
            </div>

            {/* Turnitin-Style Side-by-Side Split Document Comparator Modal */}
            {comparatorData && (
                <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                    <div className="bg-white rounded-3xl shadow-2xl border border-gray-200 max-w-5xl w-full max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                        {/* Comparator Modal Header */}
                        <div className="p-6 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800">
                            <div className="flex items-center gap-3">
                                <div className="p-2.5 bg-indigo-500/20 text-indigo-400 rounded-xl border border-indigo-500/30">
                                    <Split className="h-5 w-5" />
                                </div>
                                <div>
                                    <h3 className="text-lg font-bold text-white">Dual-Pane Synchronized Comparator</h3>
                                    <p className="text-xs text-slate-400 flex items-center gap-2">
                                        <span>Suspect Document vs.</span>
                                        <span className="text-indigo-400 font-semibold truncate max-w-sm">{comparatorData.sourceTitle}</span>
                                        <span className="px-2 py-0.2 bg-red-900/60 text-red-300 border border-red-700 rounded text-[10px] font-bold">
                                            {comparatorData.matchType}
                                        </span>
                                    </p>
                                </div>
                            </div>

                            <button
                                onClick={() => setComparatorData(null)}
                                className="p-2 text-slate-400 hover:text-white rounded-xl hover:bg-slate-800 transition-all"
                            >
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        {/* Comparator Body: Dual Panes */}
                        <div className="p-6 overflow-y-auto flex-1 grid grid-cols-1 md:grid-cols-2 gap-6 bg-slate-50">
                            {/* Left Pane: Suspect Document */}
                            <div className="bg-white border-2 border-red-200 rounded-2xl p-5 shadow-sm flex flex-col">
                                <div className="flex items-center justify-between pb-3 mb-3 border-b border-red-100">
                                    <span className="text-xs font-black uppercase tracking-wider text-red-700 flex items-center gap-1.5">
                                        <FileText className="h-4 w-4 text-red-500" />
                                        Your Uploaded Document (Suspect)
                                    </span>
                                    <span className="text-[10px] font-bold bg-red-100 text-red-800 px-2 py-0.5 rounded">
                                        Token Diff Overlap
                                    </span>
                                </div>
                                <div className="text-sm leading-relaxed text-slate-800 font-serif flex-1">
                                    {renderDiffTokens(comparatorData.suspectText, comparatorData.sourceText, 'red')}
                                </div>
                            </div>

                            {/* Right Pane: Live Source / Archive Match */}
                            <div className="bg-white border-2 border-emerald-200 rounded-2xl p-5 shadow-sm flex flex-col">
                                <div className="flex items-center justify-between pb-3 mb-3 border-b border-emerald-100">
                                    <span className="text-xs font-black uppercase tracking-wider text-emerald-700 flex items-center gap-1.5 truncate max-w-xs">
                                        <Globe className="h-4 w-4 text-emerald-500" />
                                        {comparatorData.sourceTitle}
                                    </span>
                                    {comparatorData.sourceUrl && (
                                        <a
                                            href={comparatorData.sourceUrl}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="text-[10px] font-bold bg-emerald-100 text-emerald-800 hover:bg-emerald-200 px-2 py-0.5 rounded flex items-center gap-1 transition-all"
                                        >
                                            <span>Visit Live</span>
                                            <ExternalLink className="h-2.5 w-2.5" />
                                        </a>
                                    )}
                                </div>
                                <div className="text-sm leading-relaxed text-slate-800 font-serif flex-1">
                                    {renderDiffTokens(comparatorData.sourceText, comparatorData.suspectText, 'emerald')}
                                </div>
                            </div>
                        </div>

                        {/* Comparator Footer */}
                        <div className="p-4 bg-white border-t border-gray-200 flex items-center justify-between text-xs text-gray-500">
                            <div className="flex items-center gap-4">
                                <span className="flex items-center gap-1.5">
                                    <span className="w-3 h-3 rounded bg-red-200 border border-red-300"></span>
                                    Matched tokens in suspect text
                                </span>
                                <span className="flex items-center gap-1.5">
                                    <span className="w-3 h-3 rounded bg-emerald-200 border border-emerald-300"></span>
                                    Corroborating tokens in source prose
                                </span>
                            </div>

                            <button
                                onClick={() => setComparatorData(null)}
                                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl font-bold transition-all"
                            >
                                Close Comparison
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* 1-Click "Fix & Cite" Assistant Modal */}
            {citeModalData && (() => {
                const citations = generateCitations({
                    title: citeModalData.title,
                    url: citeModalData.url
                });

                return (
                    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
                        <div className="bg-white rounded-3xl shadow-2xl border border-gray-200 max-w-2xl w-full flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
                            {/* Header */}
                            <div className="p-6 bg-gradient-to-r from-purple-700 to-indigo-700 text-white flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    <div className="p-2.5 bg-white/20 rounded-xl">
                                        <Sparkles className="h-6 w-6 text-white" />
                                    </div>
                                    <div>
                                        <h3 className="text-lg font-bold">1-Click "Fix &amp; Cite" Assistant</h3>
                                        <p className="text-xs text-purple-200">Generate academic citations and ethical attribution formats.</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setCiteModalData(null)}
                                    className="p-2 text-white/80 hover:text-white rounded-xl hover:bg-white/10 transition-all"
                                >
                                    <X className="h-5 w-5" />
                                </button>
                            </div>

                            {/* Body */}
                            <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
                                {/* Matched Passage */}
                                <div>
                                    <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-1.5">Flagged Sentence</p>
                                    <p className="text-xs sm:text-sm text-gray-800 bg-purple-50/60 p-3 rounded-xl border border-purple-200 italic">
                                        "{citeModalData.sentence}"
                                    </p>
                                </div>

                                {/* Ethical Paraphrase Suggestion */}
                                <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4">
                                    <p className="text-xs font-bold text-amber-900 uppercase tracking-wider mb-1 flex items-center gap-1.5">
                                        <CheckCircle className="h-3.5 w-3.5 text-amber-600" />
                                        Ethical Attribution Recommendation
                                    </p>
                                    <p className="text-xs text-amber-800 leading-relaxed">
                                        To maintain academic honesty, attribute the claim to the source author or publication directly. For example:
                                        <span className="font-semibold block mt-1 text-gray-900 bg-white p-2.5 rounded-lg border border-amber-200">
                                            According to {citeModalData.title || 'the source'}, "{citeModalData.sentence}" ({new Date().getFullYear()}).
                                        </span>
                                    </p>
                                </div>

                                {/* Citation Formats */}
                                <div>
                                    <p className="text-xs font-bold text-gray-500 uppercase tracking-wider mb-3">Academic Formats (1-Click Copy)</p>
                                    <div className="space-y-3">
                                        {/* APA 7 */}
                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 flex items-center justify-between gap-3">
                                            <div className="flex-1">
                                                <span className="text-[10px] font-black uppercase text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">APA 7th</span>
                                                <p className="text-xs text-gray-800 mt-1 font-serif">{citations.apa}</p>
                                            </div>
                                            <button
                                                onClick={() => handleCopyCitation(citations.apa, 'apa')}
                                                className="px-3 py-1.5 bg-white border border-gray-300 hover:border-indigo-400 text-gray-700 hover:text-indigo-600 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1 shrink-0"
                                            >
                                                {copiedFormat === 'apa' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                                                <span>{copiedFormat === 'apa' ? 'Copied' : 'Copy'}</span>
                                            </button>
                                        </div>

                                        {/* MLA 9 */}
                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 flex items-center justify-between gap-3">
                                            <div className="flex-1">
                                                <span className="text-[10px] font-black uppercase text-purple-600 bg-purple-50 px-2 py-0.5 rounded">MLA 9th</span>
                                                <p className="text-xs text-gray-800 mt-1 font-serif">{citations.mla}</p>
                                            </div>
                                            <button
                                                onClick={() => handleCopyCitation(citations.mla, 'mla')}
                                                className="px-3 py-1.5 bg-white border border-gray-300 hover:border-purple-400 text-gray-700 hover:text-purple-600 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1 shrink-0"
                                            >
                                                {copiedFormat === 'mla' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                                                <span>{copiedFormat === 'mla' ? 'Copied' : 'Copy'}</span>
                                            </button>
                                        </div>

                                        {/* Chicago */}
                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 flex items-center justify-between gap-3">
                                            <div className="flex-1">
                                                <span className="text-[10px] font-black uppercase text-blue-600 bg-blue-50 px-2 py-0.5 rounded">Chicago 17th</span>
                                                <p className="text-xs text-gray-800 mt-1 font-serif">{citations.chicago}</p>
                                            </div>
                                            <button
                                                onClick={() => handleCopyCitation(citations.chicago, 'chicago')}
                                                className="px-3 py-1.5 bg-white border border-gray-300 hover:border-blue-400 text-gray-700 hover:text-blue-600 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1 shrink-0"
                                            >
                                                {copiedFormat === 'chicago' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                                                <span>{copiedFormat === 'chicago' ? 'Copied' : 'Copy'}</span>
                                            </button>
                                        </div>

                                        {/* Harvard */}
                                        <div className="bg-slate-50 border border-gray-200 rounded-xl p-3.5 flex items-center justify-between gap-3">
                                            <div className="flex-1">
                                                <span className="text-[10px] font-black uppercase text-teal-600 bg-teal-50 px-2 py-0.5 rounded">Harvard</span>
                                                <p className="text-xs text-gray-800 mt-1 font-serif">{citations.harvard}</p>
                                            </div>
                                            <button
                                                onClick={() => handleCopyCitation(citations.harvard, 'harvard')}
                                                className="px-3 py-1.5 bg-white border border-gray-300 hover:border-teal-400 text-gray-700 hover:text-teal-600 rounded-lg text-xs font-bold shadow-sm transition-all flex items-center gap-1 shrink-0"
                                            >
                                                {copiedFormat === 'harvard' ? <Check className="h-3.5 w-3.5 text-emerald-600" /> : <Copy className="h-3.5 w-3.5" />}
                                                <span>{copiedFormat === 'harvard' ? 'Copied' : 'Copy'}</span>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                );
            })()}
        </div>
    );
}
