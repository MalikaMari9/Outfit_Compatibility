import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Edit2, LogOut, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/hooks/use-toast';
import { apiUrl, getAuthHeader } from '@/lib/api';
import { clearAuthState, getAuthState } from '@/lib/auth';
import Navbar from '@/components/layout/Navbar';
import UserSidebar from '@/components/layout/UserSidebar';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

interface Profile {
  full_name: string | null;
  bio: string | null;
  avatar_url: string | null;
}

const Profile = () => {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [isEditing, setIsEditing] = useState(false);
  const [loading, setLoading] = useState(false);
  const auth = getAuthState();
  const storedEmail = auth.email;
  const storedToken = auth.token;
  const [profile, setProfile] = useState<Profile>({
    full_name: '',
    bio: '',
    avatar_url: null,
  });
  const [accountLoading, setAccountLoading] = useState(false);

  useEffect(() => {
    if (!storedToken) {
      navigate('/auth');
      return;
    }
    fetchProfile();
  }, [storedToken, navigate]);

  const fetchProfile = async () => {
    const cached = localStorage.getItem('profile');
    if (cached) {
      try {
        setProfile(JSON.parse(cached));
      } catch {
        setProfile({ full_name: '', bio: '', avatar_url: null });
      }
    }

    if (!storedToken) return;

    setAccountLoading(true);
    try {
      const response = await fetch(apiUrl('/account'), {
        headers: {
          ...getAuthHeader(),
        },
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        if (response.status === 401 || response.status === 403 || response.status === 404) {
          clearAuthState();
          navigate('/auth');
          return;
        }
        return;
      }
      const serverName = data?.user?.name || '';
      setProfile((prev) => {
        const next = {
          ...prev,
          full_name: serverName || prev.full_name || '',
        };
        localStorage.setItem('profile', JSON.stringify(next));
        return next;
      });
    } catch {
      // keep local profile if server fetch fails
    } finally {
      setAccountLoading(false);
    }
  };

  const handleSave = async () => {
    setLoading(true);

    try {
      if (storedToken) {
        const response = await fetch(apiUrl('/account'), {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            ...getAuthHeader(),
          },
          body: JSON.stringify({
            name: profile.full_name,
            bio: profile.bio,
          }),
        });
        if (!response.ok) {
          const data = await response.json().catch(() => ({}));
          const message = data?.message || 'Failed to update profile.';
          toast({
            variant: 'destructive',
            title: 'Update Failed',
            description: message,
          });
          setLoading(false);
          return;
        }
      }

      localStorage.setItem('profile', JSON.stringify({
        full_name: profile.full_name,
        bio: profile.bio,
        avatar_url: profile.avatar_url,
      }));
      toast({
        title: 'Success',
        description: 'Profile updated successfully.',
      });
      setIsEditing(false);
    } catch {
      toast({
        variant: 'destructive',
        title: 'Update Failed',
        description: 'Network error. Please try again.',
      });
    }

    setLoading(false);
  };

  const handleSignOut = async () => {
    clearAuthState();
    navigate('/auth');
  };

  const handleDeleteAccount = async () => {
    toast({
      title: 'Account Deletion',
      description: 'Please contact support to delete your account.',
    });
  };

  if (!storedToken) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Redirecting to sign in...</p>
      </div>
    );
  }

  const displayName = profile.full_name || storedEmail?.split('@')[0] || 'Your Name';
  const initialsSource = displayName.trim();
  const initials = initialsSource
    ? initialsSource.split(' ').filter(Boolean).slice(0, 2).map((part) => part[0]).join('').toUpperCase()
    : 'U';

  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <UserSidebar />

      <main className="p-6 lg:p-10">
        <div className="max-w-3xl space-y-8">
          <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div>
              <h1 className="text-4xl font-playfair font-bold">My Profile</h1>
              <p className="text-muted-foreground">
                Keep your information up to date and manage your account.
              </p>
            </div>
            {!isEditing && (
              <Button variant="outline" onClick={() => setIsEditing(true)} className="gap-2">
                <Edit2 className="h-4 w-4" />
                Edit Profile
              </Button>
            )}
          </div>

          <Card className="border-none shadow-lg">
            <CardHeader className="pb-2">
              <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                <div className="h-20 w-20 rounded-full bg-primary flex items-center justify-center">
                  {profile.avatar_url ? (
                    <img
                      src={profile.avatar_url}
                      alt="Avatar"
                      className="h-20 w-20 rounded-full object-cover"
                    />
                  ) : (
                    <span className="text-2xl font-semibold text-primary-foreground">
                      {initials}
                    </span>
                  )}
                </div>
                <div>
                  <CardTitle className="font-playfair text-2xl">
                    {accountLoading ? 'Loading...' : displayName}
                  </CardTitle>
                  <p className="text-sm text-muted-foreground">{storedEmail || 'user@example.com'}</p>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              {isEditing ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="name">Full Name</Label>
                    <Input
                      id="name"
                      value={profile.full_name || ''}
                      onChange={(e) =>
                        setProfile({ ...profile, full_name: e.target.value })
                      }
                      placeholder="Enter your name"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input id="email" value={storedEmail || ''} disabled />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="bio">Bio</Label>
                    <Textarea
                      id="bio"
                      value={profile.bio || ''}
                      onChange={(e) =>
                        setProfile({ ...profile, bio: e.target.value })
                      }
                      placeholder="Tell us about yourself..."
                      rows={4}
                    />
                  </div>

                  <div className="flex gap-4">
                    <Button onClick={handleSave} disabled={loading} className="flex-1">
                      {loading ? 'Saving...' : 'Save Changes'}
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => setIsEditing(false)}
                      className="flex-1"
                    >
                      Cancel
                    </Button>
                  </div>

                  <div className="border-t border-border pt-4">
                    <p className="text-sm font-medium text-destructive">Danger Zone</p>
                    <p className="text-sm text-muted-foreground mb-3">
                      Deleting your account is permanent. This cannot be undone.
                    </p>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="text-destructive border-destructive/40 hover:bg-destructive/10"
                        >
                          Delete Account
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Are you sure?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This action cannot be undone. This will permanently delete your
                            account and remove all your data from our servers.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={handleDeleteAccount}>
                            Delete Account
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </>
              ) : (
                <div className="space-y-4">
                  <div>
                    <Label className="text-muted-foreground">Full Name</Label>
                    <p className="mt-1 font-medium">{displayName}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Email</Label>
                    <p className="mt-1">{storedEmail || 'user@example.com'}</p>
                  </div>
                  <div>
                    <Label className="text-muted-foreground">Bio</Label>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {profile.bio || 'No bio added yet.'}
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
};

export default Profile;
