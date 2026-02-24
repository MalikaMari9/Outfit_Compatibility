import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import AdminSidebar from '@/components/layout/AdminSidebar';

const AdminSettings = () => {
  const navigate = useNavigate();
  const storedRole = typeof window !== 'undefined' ? localStorage.getItem('role') : null;
  const storedEmail = typeof window !== 'undefined' ? localStorage.getItem('email') : null;
  const roleLabel = storedRole || 'admin';
  const emailLabel = storedEmail || 'admin@example.com';

  useEffect(() => {
    if (storedRole !== 'admin') {
      navigate('/auth');
    }
  }, [storedRole, navigate]);

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
          <h1 className="text-3xl font-playfair font-bold">Settings</h1>
          <p className="text-muted-foreground mt-1">Manage your admin preferences.</p>
        </div>

        <div className="max-w-2xl space-y-6">
          {/* Account Settings */}
          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">Account Settings</CardTitle>
              <CardDescription>Your account information</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex justify-between items-center">
                <div>
                  <Label className="text-muted-foreground">Email</Label>
                  <p className="font-medium">{emailLabel}</p>
                </div>
              </div>
              <div className="flex justify-between items-center">
                <div>
                  <Label className="text-muted-foreground">Role</Label>
                  <p className="font-medium capitalize">{roleLabel}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Notification Settings */}
          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">Notifications</CardTitle>
              <CardDescription>Configure your notification preferences</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Email Notifications</Label>
                  <p className="text-sm text-muted-foreground">
                    Receive email notifications for important updates
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>Report Alerts</Label>
                  <p className="text-sm text-muted-foreground">
                    Get notified when new reports are submitted
                  </p>
                </div>
                <Switch defaultChecked />
              </div>

              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <Label>New User Alerts</Label>
                  <p className="text-sm text-muted-foreground">
                    Get notified when new users sign up
                  </p>
                </div>
                <Switch />
              </div>
            </CardContent>
          </Card>

          {/* Appearance Settings */}
          <Card className="border-none shadow-md">
            <CardHeader>
              <CardTitle className="text-lg">Appearance</CardTitle>
              <CardDescription>Customize the dashboard appearance</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex justify-between items-center">
                <div>
                  <Label>Theme</Label>
                  <p className="text-sm text-muted-foreground">Current theme</p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-6 w-6 rounded-full bg-primary" />
                  <span className="font-medium">Wardo Sage</span>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default AdminSettings;
