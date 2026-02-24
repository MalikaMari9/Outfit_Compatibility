import Navbar from '@/components/layout/Navbar';
import Footer from '@/components/layout/Footer';

const About = () => {
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Navbar />

      <main className="container mx-auto px-4 py-16 flex-1">
        {/* Hero */}
        <div className="text-center mb-16">
          <h1 className="text-4xl md:text-5xl font-playfair font-bold mb-4">About Us</h1>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            Discover the story behind Wardo and our mission to revolutionize personal styling.
          </p>
        </div>

        {/* Our Story */}
        <section className="mb-20">
          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <h2 className="text-3xl font-playfair font-bold mb-6">Our Story</h2>
              <p className="text-muted-foreground mb-4 leading-relaxed">
                Wardo was born from a simple idea: everyone deserves to look and feel amazing without spending hours deciding what to wear. Founded in 2024, we set out to create an AI-powered fashion companion that understands your unique style.
              </p>
              <p className="text-muted-foreground mb-4 leading-relaxed">
                Our team of fashion enthusiasts and tech innovators came together with a shared vision - to democratize personal styling and make it accessible to everyone. We believe that great style isn't about following trends blindly, but about expressing your authentic self.
              </p>
              <p className="text-muted-foreground leading-relaxed">
                Today, Wardo helps thousands of users discover new outfit combinations, enhance their existing wardrobe, and build confidence in their personal style.
              </p>
            </div>
            <div className="relative">
              <img
                src="https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600&h=500&fit=crop"
                alt="Fashion studio"
                className="rounded-2xl shadow-xl"
              />
            </div>
          </div>
        </section>

        {/* Our Mission */}
        <section className="mb-20 bg-secondary/30 rounded-3xl p-12">
          <div className="max-w-3xl mx-auto text-center">
            <h2 className="text-3xl font-playfair font-bold mb-6">Our Mission</h2>
            <p className="text-lg text-muted-foreground leading-relaxed">
              To empower individuals to express their authentic selves through fashion by providing intelligent, personalized styling solutions that save time, reduce wardrobe waste, and build confidence. We're committed to making great style accessible to everyone, regardless of their fashion knowledge or budget.
            </p>
          </div>
        </section>

      </main>

      <Footer />
    </div>
  );
};

export default About;
