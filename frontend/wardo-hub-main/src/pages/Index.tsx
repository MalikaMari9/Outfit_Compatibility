import { Link } from 'react-router-dom';
import { ArrowRight, Sparkles, Palette, TrendingUp, Clock } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';

// Demo fashion images for masonry grid
const fashionImages = [
  { id: 1, src: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=400&h=600&fit=crop', alt: 'Fashion model 1' },
  { id: 2, src: 'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=400&h=500&fit=crop', alt: 'Fashion model 2' },
  { id: 3, src: 'https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=400&h=700&fit=crop', alt: 'Fashion model 3' },
  { id: 4, src: 'https://images.unsplash.com/photo-1509631179647-0177331693ae?w=400&h=550&fit=crop', alt: 'Fashion model 4' },
  { id: 6, src: 'https://images.unsplash.com/photo-1469334031218-e382a71b716b?w=400&h=650&fit=crop', alt: 'Fashion model 6' },
  { id: 7, src: 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=400&h=500&fit=crop', alt: 'Fashion model 7' },
  { id: 8, src: 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=400&h=600&fit=crop', alt: 'Fashion model 8' },
];

const features = [
  {
    icon: Sparkles,
    title: 'Smart AI-Powered Styling',
    description: 'Our advanced AI analyzes your wardrobe and suggests perfect outfit combinations.',
  },
  {
    icon: Palette,
    title: 'Personalized Outfit Recommendations',
    description: 'Get tailored suggestions based on your style preferences and body type.',
  },
  {
    icon: TrendingUp,
    title: 'Match Percentage Analysis',
    description: 'See how well your outfit pieces work together with our compatibility scoring.',
  },
  {
    icon: Clock,
    title: 'Time-Saving & Convenient',
    description: 'Spend less time deciding what to wear and more time looking fabulous.',
  },
];

const Index = () => {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />

      <main className="flex-1">
        {/* Hero Section */}
        <section className="relative py-20 md:py-32 overflow-hidden">
          <div className="container mx-auto px-4">
            <div className="max-w-3xl mx-auto text-center">
              <h1 className="text-4xl md:text-6xl font-playfair font-bold text-foreground mb-6 animate-fade-in">
                What's Trending in 2026
              </h1>
              <p className="text-lg md:text-xl text-muted-foreground mb-8 animate-fade-in">
                Discover the latest fashion trends and elevate your style with AI-powered outfit recommendations.
              </p>
              <div className="flex flex-col sm:flex-row gap-4 justify-center animate-fade-in">
                <Button asChild size="lg" className="bg-primary text-primary-foreground hover:bg-primary/90">
                  <Link to="/style-studio">
                    Explore Style Studio
                    <ArrowRight className="ml-2 h-5 w-5" />
                  </Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link to="/about">Learn More</Link>
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* Pinterest-style Masonry Grid */}
        <section className="py-16 bg-secondary/30">
          <div className="container mx-auto px-4">
            <h2 className="text-3xl md:text-4xl font-playfair font-bold text-center mb-12">
              Trending Styles
            </h2>
            <div className="masonry-grid">
              {fashionImages.map((image) => (
                <div key={image.id} className="masonry-item">
                  <div className="relative group overflow-hidden rounded-xl shadow-lg">
                    <img
                      src={image.src}
                      alt={image.alt}
                      className="w-full object-cover transition-transform duration-300 group-hover:scale-105"
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Fashion Article Section */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <div className="grid md:grid-cols-2 gap-12 items-center">
              <div>
                <h2 className="text-3xl md:text-4xl font-playfair font-bold mb-6">
                  Elevate Your Fashion Game
                </h2>
                <p className="text-muted-foreground mb-6 leading-relaxed">
                  Fashion is more than just clothing - it's a form of self-expression. At Wardo, we believe everyone deserves to look and feel their best. Our AI-powered platform helps you discover new styles, create stunning outfit combinations, and stay ahead of the latest trends.
                </p>
                <p className="text-muted-foreground mb-8 leading-relaxed">
                  Whether you're dressing for a casual day out or a special occasion, our Style Studio provides personalized recommendations tailored just for you. Join thousands of fashion enthusiasts who have transformed their wardrobes with Wardo.
                </p>
                <Button asChild className="bg-accent text-accent-foreground hover:bg-accent/90">
                  <Link to="/style-studio">
                    Get Started
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </div>
              <div className="relative">
                <img
                  src="https://images.unsplash.com/photo-1490481651871-ab68de25d43d?w=600&h=700&fit=crop"
                  alt="Fashion showcase"
                  className="rounded-2xl shadow-2xl"
                />
                <div className="absolute -bottom-6 -left-6 bg-card p-6 rounded-xl shadow-lg">
                  <p className="text-3xl font-playfair font-bold text-accent">10K+</p>
                  <p className="text-sm text-muted-foreground">Happy Users</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Why Choose Us */}
        <section className="py-20 bg-secondary/30">
          <div className="container mx-auto px-4">
            <h2 className="text-3xl md:text-4xl font-playfair font-bold text-center mb-4">
              Why Choose Us
            </h2>
            <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
              Experience the future of fashion with our innovative AI-powered styling tools.
            </p>
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
              {features.map((feature, index) => (
                <Card key={index} className="bg-card border-none shadow-lg hover:shadow-xl transition-shadow">
                  <CardContent className="p-6 text-center">
                    <div className="h-14 w-14 bg-primary/10 rounded-full flex items-center justify-center mx-auto mb-4">
                      <feature.icon className="h-7 w-7 text-primary" />
                    </div>
                    <h3 className="font-semibold text-lg mb-2">{feature.title}</h3>
                    <p className="text-sm text-muted-foreground">{feature.description}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        {/* CTA Section */}
        <section className="py-20">
          <div className="container mx-auto px-4">
            <div className="bg-primary rounded-3xl p-12 text-center">
              <h2 className="text-3xl md:text-4xl font-playfair font-bold text-primary-foreground mb-4">
                Ready to Transform Your Style?
              </h2>
              <p className="text-primary-foreground/80 mb-8 max-w-xl mx-auto">
                Join Wardo today and discover a whole new world of fashion possibilities.
              </p>
              <Button asChild size="lg" className="bg-card text-foreground hover:bg-card/90">
                <Link to="/auth?tab=signup">
                  Sign Up for Free
                  <ArrowRight className="ml-2 h-5 w-5" />
                </Link>
              </Button>
            </div>
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default Index;
