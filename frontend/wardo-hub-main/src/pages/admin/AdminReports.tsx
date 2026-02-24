import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, MoreHorizontal, Eye, CheckCircle2, XCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { apiUrl, getAuthHeader } from '@/lib/api';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useToast } from '@/hooks/use-toast';
import AdminSidebar from '@/components/layout/AdminSidebar';

type ReportStatus = 'pending' | 'resolved' | 'dismissed';
type ReportCategoryKey = 'mixmatch' | 'glowup' | 'compatibility' | 'recommend' | 'other';

type AdminReport = {
  id: string;
  user: string;
  userEmail: string;
  categoryKey: ReportCategoryKey;
  category: string;
  description: string;
  status: ReportStatus;
  submitted: string;
  updated: string;
  details: Record<string, unknown>;
};

const CATEGORY_LABELS: Record<ReportCategoryKey, string> = {
  mixmatch: 'Mix & Match',
  glowup: 'Glow Up',
  compatibility: 'Compatibility',
  recommend: 'Recommend',
  other: 'Other',
};

const toReportCategory = (value: unknown): ReportCategoryKey => {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'mixmatch') return 'mixmatch';
  if (raw === 'glowup') return 'glowup';
  if (raw === 'compatibility') return 'compatibility';
  if (raw === 'recommend') return 'recommend';
  return 'other';
};

const toReportStatus = (value: unknown): ReportStatus => {
  const raw = String(value || '').trim().toLowerCase();
  if (raw === 'resolved') return 'resolved';
  if (raw === 'dismissed') return 'dismissed';
  return 'pending';
};

const toStatusLabel = (status: ReportStatus): string => status.charAt(0).toUpperCase() + status.slice(1);

const parseReport = (raw: Record<string, unknown>): AdminReport => {
  const categoryKey = toReportCategory(raw.page);
  const status = toReportStatus(raw.status);
  const userObj = raw.user && typeof raw.user === 'object' ? (raw.user as Record<string, unknown>) : null;
  const userName = String(userObj?.name || '').trim() || 'Anonymous User';
  const userEmail = String(userObj?.email || '').trim();
  const details = raw.details && typeof raw.details === 'object' ? (raw.details as Record<string, unknown>) : {};

  return {
    id: String(raw._id || ''),
    user: userName,
    userEmail,
    categoryKey,
    category: CATEGORY_LABELS[categoryKey],
    description: String(raw.message || '').trim() || '(No message)',
    status,
    submitted: String(raw.createdAt || new Date().toISOString()),
    updated: String(raw.updatedAt || raw.createdAt || new Date().toISOString()),
    details,
  };
};

const AdminReports = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [reports, setReports] = useState<AdminReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);
  const [viewOpen, setViewOpen] = useState(false);
  const [viewLoading, setViewLoading] = useState(false);
  const [selectedReport, setSelectedReport] = useState<AdminReport | null>(null);

  const storedRole = typeof window !== 'undefined' ? localStorage.getItem('role') : null;

  useEffect(() => {
    if (storedRole !== 'admin') {
      navigate('/auth');
    }
  }, [storedRole, navigate]);

  useEffect(() => {
    if (storedRole === 'admin') {
      void fetchReports();
    }
  }, [storedRole]);

  const handleUnauthorized = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('role');
    toast({
      variant: 'destructive',
      title: 'Session Expired',
      description: 'Please sign in again.',
    });
    navigate('/auth');
  };

  const fetchReports = async () => {
    setLoading(true);
    try {
      const response = await fetch(apiUrl('/admin/reports?limit=200'), {
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return;
        }
        const message = data?.message || 'Failed to load reports.';
        toast({
          variant: 'destructive',
          title: 'Fetch Failed',
          description: message,
        });
        return;
      }

      const mapped = Array.isArray(data.reports)
        ? data.reports
            .filter((row: unknown) => row && typeof row === 'object')
            .map((row: unknown) => parseReport(row as Record<string, unknown>))
        : [];
      setReports(mapped);
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Fetch Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  const filteredReports = reports.filter((r) => {
    const q = searchQuery.toLowerCase();
    const matchesSearch =
      r.user.toLowerCase().includes(q) ||
      r.userEmail.toLowerCase().includes(q) ||
      r.description.toLowerCase().includes(q);
    const matchesCategory = categoryFilter === 'all' || r.categoryKey === categoryFilter;
    const matchesStatus = statusFilter === 'all' || r.status === statusFilter;
    return matchesSearch && matchesCategory && matchesStatus;
  });

  const applyReportStatus = async (reportId: string, status: ReportStatus) => {
    setUpdatingId(reportId);
    try {
      const response = await fetch(apiUrl(`/admin/reports/${reportId}`), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeader(),
        },
        body: JSON.stringify({ status }),
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return;
        }
        toast({
          variant: 'destructive',
          title: 'Update Failed',
          description: data?.message || 'Failed to update report.',
        });
        return;
      }

      const reportRaw = data?.report && typeof data.report === 'object' ? data.report : null;
      if (reportRaw) {
        const updated = parseReport(reportRaw as Record<string, unknown>);
        setReports((prev) => prev.map((r) => (r.id === reportId ? updated : r)));
        if (selectedReport?.id === reportId) {
          setSelectedReport(updated);
        }
      } else {
        setReports((prev) => prev.map((r) => (r.id === reportId ? { ...r, status } : r)));
      }

      toast({
        title: status === 'resolved' ? 'Report Resolved' : 'Report Dismissed',
        description:
          status === 'resolved'
            ? 'The report has been marked as resolved.'
            : 'The report has been marked as dismissed.',
      });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Update Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setUpdatingId(null);
    }
  };

  const handleView = async (reportId: string) => {
    setViewOpen(true);
    setViewLoading(true);
    try {
      const response = await fetch(apiUrl(`/admin/reports/${reportId}`), {
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          handleUnauthorized();
          return;
        }
        toast({
          variant: 'destructive',
          title: 'Fetch Failed',
          description: data?.message || 'Failed to load report details.',
        });
        setViewOpen(false);
        return;
      }

      const reportRaw = data?.report && typeof data.report === 'object' ? data.report : null;
      if (reportRaw) {
        setSelectedReport(parseReport(reportRaw as Record<string, unknown>));
      } else {
        setSelectedReport(reports.find((r) => r.id === reportId) || null);
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Fetch Failed',
        description: 'Network error. Please try again.',
      });
      setViewOpen(false);
    } finally {
      setViewLoading(false);
    }
  };

  if (storedRole !== 'admin') {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Redirecting to sign in...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <AdminSidebar />

      <main className="p-6 lg:p-8 lg:ml-64">
        <div className="mb-8">
          <h1 className="text-3xl font-playfair font-bold">Reports</h1>
          <p className="text-muted-foreground mt-1">Review and manage user-submitted reports.</p>
        </div>

        <Card className="border-none shadow-md">
          <CardHeader>
            <div className="flex flex-col lg:flex-row gap-4 justify-between">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search reports..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              <div className="flex gap-4">
                <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                  <SelectTrigger className="w-44">
                    <SelectValue placeholder="Category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Categories</SelectItem>
                    <SelectItem value="glowup">Glow Up</SelectItem>
                    <SelectItem value="mixmatch">Mix & Match</SelectItem>
                    <SelectItem value="compatibility">Compatibility</SelectItem>
                    <SelectItem value="recommend">Recommend</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger className="w-40">
                    <SelectValue placeholder="Status" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="pending">Pending</SelectItem>
                    <SelectItem value="resolved">Resolved</SelectItem>
                    <SelectItem value="dismissed">Dismissed</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="text-center py-12">
                <p className="text-muted-foreground">Loading reports...</p>
              </div>
            ) : filteredReports.length === 0 ? (
              <div className="text-center py-12">
                <p className="text-muted-foreground">No reports found.</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Report Details</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Submitted</TableHead>
                    <TableHead className="text-right">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredReports.map((report) => (
                    <TableRow key={report.id}>
                      <TableCell>
                        <div>
                          <p className="font-medium">{report.user}</p>
                          {report.userEmail && (
                            <p className="text-xs text-muted-foreground">{report.userEmail}</p>
                          )}
                          <p className="text-sm text-muted-foreground line-clamp-1">
                            {report.description}
                          </p>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{report.category}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={report.status === 'resolved' ? 'default' : 'secondary'}
                          className={
                            report.status === 'resolved'
                              ? 'bg-primary/10 text-primary hover:bg-primary/20'
                              : report.status === 'pending'
                                ? 'bg-destructive/10 text-destructive hover:bg-destructive/20'
                                : ''
                          }
                        >
                          {toStatusLabel(report.status)}
                        </Badge>
                      </TableCell>
                      <TableCell>{new Date(report.submitted).toLocaleDateString()}</TableCell>
                      <TableCell className="text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" disabled={updatingId === report.id}>
                              <MoreHorizontal className="h-4 w-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => void handleView(report.id)}>
                              <Eye className="h-4 w-4 mr-2" />
                              View Details
                            </DropdownMenuItem>
                            {report.status === 'pending' && (
                              <DropdownMenuItem onClick={() => void applyReportStatus(report.id, 'resolved')}>
                                <CheckCircle2 className="h-4 w-4 mr-2" />
                                Resolve
                              </DropdownMenuItem>
                            )}
                            {report.status !== 'dismissed' && (
                              <DropdownMenuItem
                                onClick={() => void applyReportStatus(report.id, 'dismissed')}
                                className="text-destructive"
                              >
                                <XCircle className="h-4 w-4 mr-2" />
                                Dismiss
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </main>

      <Dialog open={viewOpen} onOpenChange={setViewOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Report Details</DialogTitle>
          </DialogHeader>
          {viewLoading || !selectedReport ? (
            <div className="py-6 text-center text-muted-foreground">Loading report...</div>
          ) : (
            <div className="space-y-4 text-sm">
              <div className="grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Reporter</p>
                  <p className="font-medium">{selectedReport.user}</p>
                  {selectedReport.userEmail && (
                    <p className="text-xs text-muted-foreground">{selectedReport.userEmail}</p>
                  )}
                </div>
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Category</p>
                  <p className="font-medium">{selectedReport.category}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Status</p>
                  <p className="font-medium">{toStatusLabel(selectedReport.status)}</p>
                </div>
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Submitted</p>
                  <p className="font-medium">{new Date(selectedReport.submitted).toLocaleString()}</p>
                </div>
              </div>
              <div>
                <p className="text-xs uppercase text-muted-foreground">Message</p>
                <p className="mt-1 whitespace-pre-wrap rounded-md border border-border bg-secondary/20 p-3">
                  {selectedReport.description}
                </p>
              </div>
              {Object.keys(selectedReport.details || {}).length > 0 && (
                <div>
                  <p className="text-xs uppercase text-muted-foreground">Technical Details</p>
                  <pre className="mt-1 max-h-56 overflow-auto rounded-md border border-border bg-secondary/20 p-3 text-xs">
                    {JSON.stringify(selectedReport.details, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default AdminReports;
