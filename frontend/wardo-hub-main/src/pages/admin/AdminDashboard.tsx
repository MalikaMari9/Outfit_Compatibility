import { useEffect, useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { Users, UserPlus, Activity, Upload, Sparkles, Layers, FileText, CheckCircle2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import AdminSidebar from '@/components/layout/AdminSidebar';
import { apiUrl, getAuthHeader } from '@/lib/api';
import { clearAuthState, getAuthState } from '@/lib/auth';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

type UserGrowthPoint = {
  month: string;
  users: number;
};

type AdminDashboardSummary = {
  totalUsers: number;
  newSignups7d: number;
  newUsers30d: number;
  totalUploads: number;
  pendingReports: number;
  resolvedReports: number;
};

const fallbackUserGrowthData: UserGrowthPoint[] = [
  { month: 'Jan', users: 120 },
  { month: 'Feb', users: 180 },
  { month: 'Mar', users: 250 },
  { month: 'Apr', users: 340 },
  { month: 'May', users: 420 },
  { month: 'Jun', users: 580 },
];

const featureUsageData = [
  { name: 'Glow Up', usage: 450 },
  { name: 'Mix & Match', usage: 380 },
  { name: 'Wardrobe', usage: 220 },
];

const AdminDashboard = () => {
  const navigate = useNavigate();
  const auth = getAuthState();
  const [loadingSummary, setLoadingSummary] = useState(false);
  const [summary, setSummary] = useState<AdminDashboardSummary | null>(null);
  const [userGrowthData, setUserGrowthData] = useState<UserGrowthPoint[]>(fallbackUserGrowthData);

  useEffect(() => {
    if (!auth.isAdmin) return;
    let cancelled = false;

    const fetchSummary = async () => {
      setLoadingSummary(true);
      try {
        const response = await fetch(apiUrl('/admin/dashboard-summary'), {
          headers: {
            ...getAuthHeader(),
          },
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (response.status === 401 || response.status === 403) {
            clearAuthState();
            navigate('/auth');
          }
          return;
        }
        if (cancelled) return;

        const liveSummary: AdminDashboardSummary = {
          totalUsers: Number(payload?.summary?.totalUsers) || 0,
          newSignups7d: Number(payload?.summary?.newSignups7d) || 0,
          newUsers30d: Number(payload?.summary?.newUsers30d) || 0,
          totalUploads: Number(payload?.summary?.totalUploads) || 0,
          pendingReports: Number(payload?.summary?.pendingReports) || 0,
          resolvedReports: Number(payload?.summary?.resolvedReports) || 0,
        };
        setSummary(liveSummary);

        const points = Array.isArray(payload?.userGrowth)
          ? payload.userGrowth
              .map((row: unknown) => {
                if (!row || typeof row !== 'object') return null;
                const rec = row as Record<string, unknown>;
                const month = String(rec.month || '').trim();
                if (!month) return null;
                return {
                  month,
                  users: Number(rec.users) || 0,
                };
              })
              .filter((row: UserGrowthPoint | null): row is UserGrowthPoint => row !== null)
          : [];
        if (points.length > 0) {
          setUserGrowthData(points);
        }
      } catch {
        // Keep fallback dashboard values if summary fetch fails.
      } finally {
        if (!cancelled) setLoadingSummary(false);
      }
    };

    void fetchSummary();
    return () => {
      cancelled = true;
    };
  }, [auth.isAdmin, navigate]);

  if (!auth.isAdmin) {
    return <Navigate to="/auth" replace />;
  }

  const fmt = (value: number): string => new Intl.NumberFormat().format(value);

  const stats = [
    { title: 'Total Users', value: summary ? fmt(summary.totalUsers) : '1,234', icon: Users, change: '+12%' },
    { title: 'New Signups', value: summary ? fmt(summary.newSignups7d) : '89', icon: UserPlus, subtitle: 'Last 7 days' },
    { title: 'New Users (30d)', value: summary ? fmt(summary.newUsers30d) : '567', icon: Activity, subtitle: 'Last 30 days' },
    { title: 'Total Uploads', value: summary ? fmt(summary.totalUploads) : '3,456', icon: Upload, change: '+8%' },
  ];

  const featureStats = [
    { title: 'Glow Up Usage', value: '450', icon: Sparkles, color: 'bg-accent/10 text-accent' },
    { title: 'Mix & Match Usage', value: '380', icon: Layers, color: 'bg-primary/10 text-primary' },
    {
      title: 'Pending Reports',
      value: summary ? fmt(summary.pendingReports) : '12',
      icon: FileText,
      color: 'bg-destructive/10 text-destructive',
    },
    {
      title: 'Resolved Reports',
      value: summary ? fmt(summary.resolvedReports) : '45',
      icon: CheckCircle2,
      color: 'bg-primary/10 text-primary',
    },
  ];

  return (
    <div className="min-h-screen bg-background">
      <AdminSidebar />

      <main className="p-6 lg:p-8 lg:ml-64">
        <div className="mb-8">
          <h1 className="text-3xl font-playfair font-bold">Welcome back, Admin</h1>
          <p className="text-muted-foreground mt-1">
            Here's what's happening with Wardo today.
          </p>
          <p className="text-xs text-muted-foreground mt-2">
            Live data: users, uploads, reports, and user growth. Usage cards remain sample values for now.
            {loadingSummary ? ' Syncing latest numbers...' : ''}
          </p>
        </div>

        {/* Main Stats */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {stats.map((stat) => (
            <Card key={stat.title} className="border-none shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">{stat.title}</p>
                    <p className="text-3xl font-bold mt-1">{stat.value}</p>
                    {stat.change && (
                      <p className="text-sm text-primary mt-1">{stat.change}</p>
                    )}
                    {stat.subtitle && (
                      <p className="text-xs text-muted-foreground mt-1">{stat.subtitle}</p>
                    )}
                  </div>
                  <div className="h-12 w-12 rounded-full bg-secondary flex items-center justify-center">
                    <stat.icon className="h-6 w-6 text-muted-foreground" />
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Feature Stats */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {featureStats.map((stat) => (
            <Card key={stat.title} className="border-none shadow-md">
              <CardContent className="p-6">
                <div className="flex items-center gap-4">
                  <div className={`h-12 w-12 rounded-full ${stat.color} flex items-center justify-center`}>
                    <stat.icon className="h-6 w-6" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">{stat.title}</p>
                    <p className="text-2xl font-bold">{stat.value}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Admin Controls */}
        <div className="grid lg:grid-cols-2 gap-6 mb-8">
          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">User List Control</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Manage users, roles, and account status.
              </p>
              <Button onClick={() => navigate('/admin/users')}>Go to Users</Button>
            </CardContent>
          </Card>

          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">Report Control</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Review and resolve user reports.
              </p>
              <Button onClick={() => navigate('/admin/reports')}>Go to Reports</Button>
            </CardContent>
          </Card>
        </div>

        {/* Charts */}
        <div className="grid lg:grid-cols-2 gap-6">
          {/* User Growth Chart */}
          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">User Growth</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={userGrowthData}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="month" className="text-xs" />
                    <YAxis className="text-xs" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="users"
                      stroke="hsl(var(--primary))"
                      strokeWidth={2}
                      dot={{ fill: 'hsl(var(--primary))' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          {/* Feature Usage Chart */}
          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">Feature Usage</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-80">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={featureUsageData}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                    <XAxis dataKey="name" className="text-xs" />
                    <YAxis className="text-xs" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'hsl(var(--card))',
                        border: '1px solid hsl(var(--border))',
                        borderRadius: '8px',
                      }}
                    />
                    <Bar dataKey="usage" fill="hsl(var(--accent))" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default AdminDashboard;
