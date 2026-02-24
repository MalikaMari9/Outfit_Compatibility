import { Link } from 'react-router-dom';
import { Sparkles, Layers, FolderOpen } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';

const features = [
  {
    title: 'Glow Up',
    description: 'Transform your outfit with AI-powered enhancement suggestions.',
    icon: Sparkles,
    path: '/style-studio/glow-up',
    color: 'bg-accent/10 text-accent',
  },
  {
    title: 'Mix & Match',
    description: 'Check how well your outfit pieces work together with compatibility scoring.',
    icon: Layers,
    path: '/style-studio/mix-match',
    color: 'bg-primary/10 text-primary',
  },
  {
    title: 'My Wardrobe',
    description: 'View and manage your saved outfit collection.',
    icon: FolderOpen,
    path: '/style-studio/wardrobe',
    color: 'bg-secondary text-foreground',
  },
];

const StyleStudio = () => {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />

      <main className="container mx-auto px-4 py-16 flex-1">
        <div className="text-center mb-12">
          <h1 className="text-4xl md:text-5xl font-playfair font-bold mb-4">Style Studio</h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Your personal AI-powered fashion assistant. Choose a feature below to get started.
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 max-w-5xl mx-auto">
          {features.map((feature) => (
            <Link key={feature.path} to={feature.path}>
              <Card className="h-full transition-all duration-300 hover:shadow-xl hover:-translate-y-1 border-none bg-card">
                <CardHeader className="text-center pb-2">
                  <div className={`h-16 w-16 rounded-full ${feature.color} flex items-center justify-center mx-auto mb-4`}>
                    <feature.icon className="h-8 w-8" />
                  </div>
                  <CardTitle className="text-xl font-playfair">{feature.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="text-center text-base">
                    {feature.description}
                  </CardDescription>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </main>

      <Footer />
    </div>
  );
};

export default StyleStudio;
