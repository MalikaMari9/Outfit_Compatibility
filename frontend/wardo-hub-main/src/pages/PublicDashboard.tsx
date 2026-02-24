import { Link } from 'react-router-dom';
import { ArrowRight, ShieldCheck, User, Sparkles, Palette, TrendingUp } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';

const PublicDashboard = () => {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />

      <main className="container mx-auto px-4 py-10 flex-1">
        <div className="max-w-5xl mx-auto space-y-12">
          <div className="text-center space-y-3">
            <h1 className="text-4xl md:text-5xl font-playfair font-bold">Dashboard Home</h1>
            <p className="text-muted-foreground">
              Sign in or create an account to access your personalized dashboard.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button asChild size="lg">
                <Link to="/auth">Sign In</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link to="/auth?tab=signup">Sign Up</Link>
              </Button>
            </div>
          </div>

          <div className="grid gap-6 md:grid-cols-2">
            <Card className="border-0 shadow-lg">
              <CardContent className="p-6 space-y-3">
                <div className="flex items-center gap-2">
                  <ShieldCheck className="h-5 w-5 text-primary" />
                  <h2 className="text-lg font-semibold">Admin Access</h2>
                </div>
                <p className="text-sm text-muted-foreground">
                  Admins are verified on the backend. Sign in to manage users and reports.
                </p>
              </CardContent>
            </Card>

            <Card className="border-0 shadow-lg">
              <CardContent className="p-6 space-y-3">
                <div className="flex items-center gap-2">
                  <User className="h-5 w-5 text-primary" />
                  <h2 className="text-lg font-semibold">User Access</h2>
                </div>
                <p className="text-sm text-muted-foreground">
                  Users get a personalized dashboard with Style Studio and Profile tools.
                </p>
              </CardContent>
            </Card>
          </div>

          <section className="grid gap-6 lg:grid-cols-3">
            <Card className="border-0 shadow-lg">
              <CardContent className="p-6 space-y-2">
                <div className="flex items-center gap-2 text-primary">
                  <Sparkles className="h-5 w-5" />
                  <h3 className="font-semibold">AI Styling Insights</h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  Upload your look and let the backend deliver style feedback instantly.
                </p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-lg">
              <CardContent className="p-6 space-y-2">
                <div className="flex items-center gap-2 text-primary">
                  <Palette className="h-5 w-5" />
                  <h3 className="font-semibold">Personalized Experience</h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  Profiles help keep your wardrobe, preferences, and history in one place.
                </p>
              </CardContent>
            </Card>
            <Card className="border-0 shadow-lg">
              <CardContent className="p-6 space-y-2">
                <div className="flex items-center gap-2 text-primary">
                  <TrendingUp className="h-5 w-5" />
                  <h3 className="font-semibold">Better Decisions</h3>
                </div>
                <p className="text-sm text-muted-foreground">
                  See compatibility and recommendations returned by the server in seconds.
                </p>
              </CardContent>
            </Card>
          </section>

          <section className="bg-secondary/40 rounded-2xl p-8 text-center space-y-3">
            <h2 className="text-2xl font-playfair font-bold">Ready to get started?</h2>
            <p className="text-muted-foreground">
              Sign in to unlock your dashboard or create a new account in seconds.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Button asChild size="lg">
                <Link to="/auth">Sign In</Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link to="/auth?tab=signup">Create Account</Link>
              </Button>
            </div>
          </section>

          <div className="text-center">
            <Button asChild variant="ghost">
              <Link to="/about">
                Learn more about Wardo
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default PublicDashboard;
