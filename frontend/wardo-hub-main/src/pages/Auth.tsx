import { useState, useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/hooks/use-toast';
import Navbar from '@/components/layout/Navbar';
import { apiUrl } from '@/lib/api';
import { getAuthState, storeAuthState } from '@/lib/auth';

const Auth = () => {

  const formatResponse = (data) => {
    if (data == null) return '';
    if (typeof data === 'string') return data;
    if (data?.message) return data.message;
    return JSON.stringify(data);
  };

  const getRoleFromResponse = (data) => {
    return data?.role || data?.userRole || data?.user?.role || data?.data?.role || null;
  };

  const getTokenFromResponse = (data) => {
    return (
      data?.token ||
      data?.access_token ||
      data?.accessToken ||
      data?.data?.token ||
      data?.data?.access_token ||
      data?.data?.accessToken ||
      null
    );
  };

  const [searchParams] = useSearchParams();
  const defaultTab = searchParams.get('tab') === 'signup' ? 'signup' : 'signin';
  const [activeTab, setActiveTab] = useState(defaultTab);

  // Sign In state
  const [signInEmail, setSignInEmail] = useState('');
  const [signInPassword, setSignInPassword] = useState('');
  const [showSignInPassword, setShowSignInPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  // Sign Up state
  const [signUpEmail, setSignUpEmail] = useState('');
  const [signUpPassword, setSignUpPassword] = useState('');
  const [signUpName, setSignUpName] = useState('');
  const [showSignUpPassword, setShowSignUpPassword] = useState(false);

  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  // Redirect if already logged in
  useEffect(() => {
    const auth = getAuthState();
    if (!auth.isAuthenticated) {
      return;
    }
    if (auth.role === 'admin') {
      navigate('/admin');
      return;
    }
    if (auth.role === 'user') {
      navigate('/dashboard');
    }
  }, [navigate]);

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const response = await fetch(apiUrl('/signin'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: signInEmail,
          password: signInPassword,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const message = data?.message || data?.error || 'Invalid email or password.';
        toast({
          variant: 'destructive',
          title: 'Sign In Failed',
          description: formatResponse(data) || message,
        });
      } else {
        const role = getRoleFromResponse(data) || 'user';
        const token = getTokenFromResponse(data);
        const email = data?.email || data?.user?.email || signInEmail;
        if (!token) {
          toast({
            variant: 'destructive',
            title: 'Sign In Failed',
            description: 'Authentication token missing from server response.',
          });
          return;
        }
        storeAuthState({ token, role, email });
        toast({
          title: 'Welcome back!',
          description: formatResponse(data),
        });
        if (role === 'admin') {
          navigate('/admin');
        } else {
          navigate('/dashboard');
        }
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Sign In Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    if (!signUpName.trim()) {
      toast({
        variant: 'destructive',
        title: 'Name Required',
        description: 'Please enter your full name.',
      });
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(apiUrl('/signup'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: signUpName,
          email: signUpEmail,
          password: signUpPassword,
        }),
      });

      const data = await response.json().catch(() => ({}));

      if (!response.ok) {
        const message = data?.message || data?.error || 'An error occurred during sign up.';
        toast({
          variant: 'destructive',
          title: 'Sign Up Failed',
          description: formatResponse(data) || message,
        });
      } else {
        const role = getRoleFromResponse(data) || 'user';
        const token = getTokenFromResponse(data);
        const email = data?.email || data?.user?.email || signUpEmail;
        if (!token) {
          toast({
            variant: 'destructive',
            title: 'Sign Up Failed',
            description: 'Authentication token missing from server response.',
          });
          return;
        }
        storeAuthState({ token, role, email });
        toast({
          title: 'Account Created!',
          description: formatResponse(data),
        });
        navigate('/dashboard');
      }
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Sign Up Failed',
        description: 'Network error. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Navbar />

      <div className="flex items-center justify-center py-12 px-4">
        <Card className="w-full max-w-md shadow-xl border-none">
          <CardHeader className="text-center">
            <CardTitle className="text-3xl font-playfair text-accent">Wardo</CardTitle>
            <CardDescription>Your AI Fashion Companion</CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-2 mb-6">
                <TabsTrigger value="signin">Sign In</TabsTrigger>
                <TabsTrigger value="signup">Sign Up</TabsTrigger>
              </TabsList>

              {/* Sign In Tab */}
              <TabsContent value="signin">
                <form onSubmit={handleSignIn} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="signin-email">Email</Label>
                    <Input
                      id="signin-email"
                      type="email"
                      placeholder="Enter your email"
                      value={signInEmail}
                      onChange={(e) => setSignInEmail(e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="signin-password">Password</Label>
                    <div className="relative">
                      <Input
                        id="signin-password"
                        type={showSignInPassword ? 'text' : 'password'}
                        placeholder="Enter your password"
                        value={signInPassword}
                        onChange={(e) => setSignInPassword(e.target.value)}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowSignInPassword(!showSignInPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showSignInPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <Checkbox
                        id="remember"
                        checked={rememberMe}
                        onCheckedChange={(checked) => setRememberMe(checked as boolean)}
                      />
                      <Label htmlFor="remember" className="text-sm text-muted-foreground">
                        Remember me
                      </Label>
                    </div>
                    <button type="button" className="text-sm text-primary hover:underline">
                      Forgot password?
                    </button>
                  </div>

                  <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? 'Signing In...' : 'Sign In'}
                  </Button>
                </form>
              </TabsContent>

              {/* Sign Up Tab */}
              <TabsContent value="signup">
                <form onSubmit={handleSignUp} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="signup-name">Full Name</Label>
                    <Input
                      id="signup-name"
                      type="text"
                      placeholder="Enter your full name"
                      value={signUpName}
                      onChange={(e) => setSignUpName(e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="signup-email">Email</Label>
                    <Input
                      id="signup-email"
                      type="email"
                      placeholder="Enter your email"
                      value={signUpEmail}
                      onChange={(e) => setSignUpEmail(e.target.value)}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="signup-password">Password</Label>
                    <div className="relative">
                      <Input
                        id="signup-password"
                        type={showSignUpPassword ? 'text' : 'password'}
                        placeholder="Create a password"
                        value={signUpPassword}
                        onChange={(e) => setSignUpPassword(e.target.value)}
                        required
                        minLength={6}
                      />
                      <button
                        type="button"
                        onClick={() => setShowSignUpPassword(!showSignUpPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                      >
                        {showSignUpPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                  <Button type="submit" className="w-full" disabled={loading}>
                    {loading ? 'Creating Account...' : 'Create Account'}
                  </Button>
                </form>
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
};

export default Auth;
